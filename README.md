# CBPi4 Tasmota S-Curve Agitator

This plugin for **CraftBeerPi4** enables the control of an agitator (mixer) or motor via a **Tasmota**-flashed device using MQTT.

The key feature of this actor is the integrated **Soft-Start and Soft-Stop (Ramping) functionality**. Instead of switching the motor on or off abruptly, the power output is regulated smoothly along an S-Curve (cosine interpolation) over a defined time period. This reduces mechanical stress on the hardware, prevents wort splashing, and ensures smoother operation.

In addition, a configurable **Start Offset** protects the motor from operating in a stalled or near-stalled condition — one of the leading causes of premature motor failure in agitator applications.

---

### Features

- **MQTT Integration:** Controls Tasmota devices directly via `cmnd` topics (PWM).
- **Soft Start:** Prevents current spikes and mechanical stress during startup.
- **Soft Stop:** Allows the agitator to decelerate smoothly to 0.
- **Proportional Ramp Time:** The configured ramp duration applies to a full 0–100% transition. Smaller changes are scaled proportionally, just like professional industrial drives.
- **Start Offset:** Instantly jumps to a configurable minimum power level before ramping, ensuring the motor starts spinning immediately and never operates in a damaging stall zone.
- **State Memory:** The actor remembers the last target power setting when toggled on/off.
- **Configurable PWM Resolution:** Supports various Tasmota `pwm_range` settings (255, 511, 1023).

---

### Hardware Requirements

This plugin communicates via **MQTT** and requires a Tasmota-flashed device capable of **PWM output**. A standard Sonoff or Shelly device is **not sufficient** — these devices do not expose GPIO-level PWM control.

**Required hardware:**
- An **ESP32-based device** flashed with [Tasmota](https://tasmota.github.io/docs/) firmware
- A **PWM motor driver** connected to a GPIO pin of the ESP32 (e.g. a dedicated PWM driver board or a suitable H-bridge/MOSFET module)
- The Tasmota device must be configured with `pwm_range` matching the **MaxPWM** parameter (255, 511, or 1023)
- MQTT broker accessible by both CraftBeerPi4 and the Tasmota device

> **Note:** Hardware documentation for a reference implementation (MashCtrl board) will be added to this repository in a future update.

---

### Installation

Install directly from the GitHub repository using `pipx`:

```bash
pipx runpip cbpi4 install https://github.com/kaeptn-h/cbpi4-tasmota-scurveagitator/archive/main.zip
```

---

### Parameters

The following settings can be configured within the Actor setup in CraftBeerPi4:

- **Topic**
  - The MQTT topic used to send the PWM value to the Tasmota device.
  - *Default:* `cmnd/tasmota_700C04/pwm6`
  - *Note:* Ensure this topic matches your Tasmota device configuration.

- **MaxPWM**
  - The maximum PWM resolution configured on the Tasmota device. Required to correctly scale percentage values (0–100%) to the device's integer PWM range.
  - *Options:* `255` (8-bit), `511` (9-bit), `1023` (10-bit).
  - *Note:* Must match the `pwm_range` setting in your Tasmota configuration.

- **RampingSeconds**
  - The duration in seconds for a full ramp from 0% to 100% (or 100% to 0%). Smaller transitions are scaled proportionally — for example, ramping from 0% to 50% takes half the configured time.
  - *Options:* 1–10 seconds.
  - *No selection:* Ramping is disabled — the motor switches on and off instantly.

- **StartOffset**
  - The minimum power level (in %) required to reliably start the motor spinning. When the motor is started from a stopped state, the output instantly jumps to this value before the S-Curve ramp begins.
  - *Options:* 5%, 10%, 15%, 20%.
  - *No selection:* No offset is applied.
  - **Important:** If a target power below the StartOffset is requested while the motor is stopped, the target is automatically raised to the offset value. A warning is written to the CBPi4 log. This behavior is intentional and protects the motor — see below.

---

### ⚠️ Motor Protection: The Start Offset

A brushless or induction motor that is commanded to run at a power level too low to overcome its own static friction will not rotate. Instead, it will sit stalled — drawing locked-rotor current (often 5–10× normal running current) while generating significant heat. Without the back-EMF that a spinning motor produces, this heat has nowhere to go. **Prolonged operation in this condition will destroy the motor windings.**

This is a well-known problem in industrial drive applications. Professional Variable Frequency Drives (VFDs) address it with a configurable **minimum frequency** or **boost voltage** setting that ensures the motor always starts with enough energy to begin rotating.

The **StartOffset** parameter serves exactly this purpose:

- When the motor is **off and commanded to start**, the output instantly jumps to the offset value — bypassing the slow bottom of the S-Curve where the motor would otherwise sit stalled.
- The S-Curve then ramps smoothly from the offset level up to the target power.
- When the motor is **already running and ramping down**, no offset is applied. A spinning motor produces back-EMF and can sustain rotation at much lower power levels than it needs to start — so the full S-Curve ramp down to 0 is safe and desirable.
- If a target power **below the offset** is requested while the motor is stopped, the plugin raises the target to the offset value automatically and logs a warning. Running continuously below the start threshold is just as dangerous as trying to start there.

**Recommended starting point:** Set StartOffset to 10% and adjust based on your motor's behavior. If the motor hums or vibrates without rotating at startup, increase the offset. Most agitator motors in homebrewing applications will start reliably between 5% and 15%.

---

### Ramping Logic (S-Curve)

To avoid abrupt movements, this plugin uses a **cosine interpolation** to shape the power ramp. Rather than a linear change, the transition starts slowly, accelerates through the middle phase, and decelerates gently as it approaches the target — forming a smooth S-shape.

**Benefits:**
1. **Mechanical Protection:** Reduces shock loads on gears, couplings, and motor bearings.
2. **Fluid Dynamics:** Minimizes sudden splashing or spillage of the mash or wort.
3. **Electrical Protection:** Avoids the current spikes associated with direct-on-line starting.

**Visual Representation:**

![S-Curve](https://upload.wikimedia.org/wikipedia/commons/8/88/Logistic-curve.svg)

*(Exemplary representation of a Sigmoid / S-Curve. Source: Wikimedia Commons)*

---

### Changelog

- **05.03.2026:** (1.0.0) Major release
  - Renamed project to `cbpi4-Tasmota-S-CurveAgitator`
  - Added **StartOffset** parameter for motor stall protection
  - Targets below StartOffset are automatically clamped with a log warning
  - Ramp time is now proportional to the actual PWM change (industrial standard behavior)
  - Improved error handling with specific exception logging
  - `Property.Select` for all numeric parameters
  - Code cleanup and full English inline documentation

- **04.03.2026:** (0.0.1) Initial Release
  - Basic implementation of the Tasmota Actor
  - Ramping logic using `asyncio` and cosine S-Curve interpolation
  - State-Memory logic
