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
                    description="Ramp duration in seconds (no selection = no ramping, instant on/off)")
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
        """Turn the actor on. If no power value is provided, restore the last remembered
        target power. Otherwise ramp up to the requested power level and update memory."""
        if power is None:
            # No power specified: restore last known target
            target = self.target_memory
        else:
            target = float(power)
            # Remember this power level for future ON calls without explicit power
            if target > 0:
                self.target_memory = target

        self.state = True
        await self.start_ramping(target)

    async def off(self):
        """Turn the actor off by ramping down to 0. The state is set to False only after
        the ramp completes to correctly reflect that the motor is still spinning down."""
        await self.start_ramping(0)
        # Note: self.state is set to False inside do_ramp() once target 0 is reached

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

        If RampingSeconds is 0, the output switches instantly (hard on/off).
        Otherwise a cosine S-curve interpolation is used: the change starts slowly,
        accelerates through the middle, and eases in at the target. This reduces
        mechanical stress and prevents wort splashing.

        The ramp is divided into (ramp_time * 10) steps with equal sleep intervals.
        MQTT publishes and CBPi UI updates happen at every step."""
        topic = self.props.get("Topic", "cmnd/tasmota_700C04/pwm6")
        max_pwm = int(self.props.get("MaxPWM", 1023))
        ramp_time = int(self.props.get("RampingSeconds", 0))  # 0 = instant switch, 1-10 = ramp

        target_pwm = int((target_percent / 100.0) * max_pwm)
        start_pwm = self.current_pwm
        pwm_diff = target_pwm - start_pwm

        if pwm_diff != 0 and ramp_time > 0:
            # Ramping mode: interpolate over (ramp_time * 10) steps using cosine S-curve
            steps = ramp_time * 10
            step_delay = ramp_time / steps

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

        # Update state flag: motor is now truly off only after ramp-down completes
        if target_percent == 0:
            self.state = False

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
