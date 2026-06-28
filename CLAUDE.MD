
# Mini Cooper R56 N14 OBD Logger Project

## Hardware
- Raspberry Pi 5, Ubuntu 24.04 LTS arm64
- WD Black SN7100 2TB NVMe via USB-C
- K+DCAN FT232RL cable (/dev/kdcan)
- Vehicle: 2007 Mini Cooper S R56, N14 turbo, 6-speed LSD manual

## Upgrades and Replacements
-r56_mini_cooper_complete_build_log.json


## Active Fault
- P0100 / DME 2B5 / 2B5F (MAF signal fault)
- New MAF installed, wiring verified, smoke test clear
- Investigating: DME adaptation, power quality, ground

## Project Structure
- 01_rpi5_setup.sh   - System setup (Ubuntu 24.04 specific)
- 02_test_connection.py - K+DCAN connection test
- 03_obd_logger.py   - Main data logger (CSV + SQLite)
- 04_analyse.py      - Post-session analysis + plots

## Key Notes
- Use Path.home() not /home/pi for all paths
- matplotlib must use Agg backend (headless server)
- dialout group required for serial port access
- python3-bluez does NOT exist on Ubuntu 24.04
