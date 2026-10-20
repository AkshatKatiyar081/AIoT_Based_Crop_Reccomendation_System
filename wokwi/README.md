# Wokwi Simulation

If you see no output in the terminal, the simulator is not running or you are watching the wrong terminal.

## Correct workflow

1) Build (once per code change):

   pio run

2) Start the simulator:

   - Press F1
   - Run: Wokwi: Start Simulator
   - Open wokwi/diagram.json before starting for the best results

3) Open the serial output:

   - Terminal dropdown -> Wokwi Terminal
   - Do not use PowerShell for serial output

## Notes

- Serial baud: 115200 (matches platformio.ini)
- Wokwi Terminal is the ESP32 serial monitor
- If you start the simulator from the workspace root, use the root-level wokwi.toml
- Ensure extension wokwi.wokwi-vscode is installed and then run Developer: Reload Window once
