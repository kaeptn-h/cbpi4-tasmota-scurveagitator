# -*- coding: utf-8 -*-
import logging
import asyncio
import math
from cbpi.api import *

logger = logging.getLogger(__name__)


@parameters([
    Property.Text(label="Topic", default_value="cmnd/tasmota_700C04/pwm6"),
    Property.Select(label="MaxPWM", options=["255", "511", "1023"]),
    Property.Select(label="RampingSeconds", options=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
                    description="Ramp duration in seconds (no selection = no ramping, instant on/off)"),
    Property.Select(label="StartOffset", options=["5", "10", "15", "20"],
                    description="Minimum PWM % to start the motor (instant jump on spin-up only). "
                                "Motor runs fine below this on spin-down, so no offset is applied there. "
                                "No selection = no offset.")
])
class TasmotaSCurveAgitator(CBPiActor):

    async def on_start(self):
        """Initialize actor state on plugin startup. Send PWM 0 to Tasmota to ensure the
        device starts in a defined OFF state, regardless of its previous state."""
        self.state = False
        self.current_pwm = 0
        self.target_memory = 100.0  # Default power level remembered for next ON command
        self.ramp_task = None

        topic = self.props.get("Topic", "cmnd/tasmota_700C04/pwm6")
        try:
            # Send PWM 0 to Tasmota to ensure device is off at startup
            await self.cbpi.satellite.publish(topic, "0")
            # Sync CBPi actor state display to 0 (no keyword args to avoid log errors)
            await self.cbpi.actor.actor_update(self.id, 0)
        except Exception as e:
            logger.warning("TasmotaSCurveAgitator: on_start publish failed: %s", e)

    async def on(self, power=None):
        """Turn the actor on. CBPi4 passes power=100 when toggling on without a specific
        power level. In that case, restore the last remembered target instead.
        Only update memory when an explicit power value other than 100 is provided."""
        if power is None or float(power) == 100:
            # CBPi4 toggle (power=100) or no power given: restore last known target
            target = self.target_memory
        else:
            target = float(power)
            # Remember this explicit power level for future ON calls
            self.target_memory = target

        self.state = True
        await self.start_ramping(target)

    async def off(self):
        """Turn the actor off by ramping down to 0. State is set to False immediately
        so CBPi4 UI reflects the off command at once, while the motor decelerates smoothly."""
        self.state = False
        await self.start_ramping(0)

    async def set_power(self, power):
        """Called by CBPi when the user adjusts the power slider. Updates the remembered
        target and ramps to the new value. Setting power to 0 is treated as OFF."""
        target = float(power)
        if target > 0:
            self.target_memory = target
            self.state = True
        # For target == 0, state will be set to False at the end of do_ramp()
        await self.start_ramping(target)

    async def start_ramping(self, target_percent):
        """Cancel any currently running ramp task and start a new one towards target_percent.
        Awaiting the cancelled task ensures it is fully cleaned up before the new one starts."""
        if self.ramp_task is not None:
            self.ramp_task.cancel()
            try:
                await self.ramp_task
            except asyncio.CancelledError:
                pass  # Expected when cancelling a running ramp
            except Exception as e:
                logger.warning("TasmotaSCurveAgitator: error while cancelling ramp task: %s", e)
        self.ramp_task = asyncio.create_task(self.do_ramp(target_percent))

    async def do_ramp(self, target_percent):
        """Drive the PWM output from the current value to target_percent.

        If RampingSeconds is not set, the output switches instantly (hard on/off).
        Otherwise a cosine S-curve interpolation is used: the change starts slowly,
        accelerates through the middle, and eases in at the target. This reduces
        mechanical stress and prevents wort splashing.

        RampingSeconds defines the time for a full 0% to 100% transition. Smaller
        changes are scaled proportionally (e.g. 0% to 50% takes half the time).

        StartOffset defines the minimum PWM % required to start the motor spinning.
        When spinning up from 0, the output jumps instantly to the offset value first,
        then the S-curve ramps from there to the target. On spin-down, no offset is
        applied since a running motor continues to turn at lower power levels.
        If the requested target is below the StartOffset, it is automatically raised
        to the offset value and a warning is logged.

        MQTT publishes and CBPi UI updates happen at every step."""
        topic = self.props.get("Topic", "cmnd/tasmota_700C04/pwm6")
        max_pwm = int(self.props.get("MaxPWM", 1023))
        ramp_time = int(self.props.get("RampingSeconds", 0))   # 0 = instant switch, 1-10 = ramp
        start_offset = int(self.props.get("StartOffset", 0))   # minimum % PWM to start motor

        # Clamp target to StartOffset minimum (only when turning on, not when stopping)
        if target_percent > 0 and target_percent < start_offset:
            logger.warning(
                "TasmotaSCurveAgitator: target %.1f%% is below StartOffset %d%% - "
                "raising target to offset value to protect the motor.",
                target_percent, start_offset
            )
            target_percent = float(start_offset)

        target_pwm = int((target_percent / 100.0) * max_pwm)
        start_pwm = self.current_pwm

        # Apply start offset only when spinning up from a stopped state
        if target_pwm > 0 and start_pwm == 0 and start_offset > 0:
            offset_pwm = int((start_offset / 100.0) * max_pwm)
            # Only apply offset if target is above the offset itself
            if target_pwm > offset_pwm:
                # Instant jump to offset so motor starts spinning immediately
                self.current_pwm = offset_pwm
                await self.cbpi.satellite.publish(topic, str(self.current_pwm))
                await self.cbpi.actor.actor_update(self.id, start_offset)
                start_pwm = offset_pwm  # S-curve starts from here

        pwm_diff = target_pwm - start_pwm

        if pwm_diff != 0 and ramp_time > 0:
            # Scale ramp time proportionally to the actual change (0->100% = full ramp_time)
            ratio = abs(pwm_diff) / max_pwm
            actual_ramp_time = ramp_time * ratio
            steps = max(1, int(actual_ramp_time * 10))
            step_delay = actual_ramp_time / steps

            for i in range(1, steps + 1):
                # Cosine interpolation produces an S-curve: slow start, fast middle, slow end
                sigmoid_p = (1 - math.cos((i / steps) * math.pi)) / 2
                self.current_pwm = int(start_pwm + (pwm_diff * sigmoid_p))
                prog_power = round((self.current_pwm / max_pwm) * 100)

                await self.cbpi.satellite.publish(topic, str(self.current_pwm))
                await self.cbpi.actor.actor_update(self.id, int(prog_power))
                await asyncio.sleep(step_delay)

        # Ensure we always reach the exact target value (covers instant switch and rounding)
        self.current_pwm = target_pwm
        await self.cbpi.satellite.publish(topic, str(self.current_pwm))
        await self.cbpi.actor.actor_update(self.id, int(target_percent))

        self.ramp_task = None

    def get_state(self):
        """Return the current logical state of the actor. Returns True while the motor is
        running or ramping up, False only after a ramp-down to 0 has fully completed."""
        return self.state

    async def run(self):
        """Required CBPi actor background loop. This actor is fully event-driven via
        on()/off()/set_power(), so no periodic work is needed here."""
        while self.running:
            await asyncio.sleep(5)


def setup(cbpi):
    cbpi.plugin.register("TasmotaSCurveAgitator", TasmotaSCurveAgitator)
