Create markdown documentation for the Mini OBD Logger project.
## Mini OBD Logger — Operating Guide

This notebook supports two workflows:

1. **First boot setup monitoring** (initial provisioning)
2. **Ongoing car session monitoring** (data collection and diagnosis)

---

### 1) First Boot Setup Monitoring (Tomorrow)

Use this once after initial power-up.

```bash
ssh lola@mini-obd.local
```

MOTD will display setup progress.

For live provisioning logs:

```bash
sudo tail -f /var/log/cloud-init-output.log
```

Quick status check:

```bash
sudo cloud-init status
```

Behavior:
- MOTD shows **IN PROGRESS** while setup runs (including venv creation).
- MOTD switches to **READY** when complete, then removes itself.

---

### 2) Car Session Monitoring

Two operating modes are available.

## Mode 1 — Autonomous Logging (No active connection)

Use when the Pi stays in the car and logs automatically.

Enable service (after validation testing):

```bash
sudo systemctl enable --now mini_obd
```

What it does:
- Starts logger on boot
- Restarts on failure/crash

After a drive, copy logs locally:

```bash
scp lola@mini-obd.local:~/mini_obd/logs/*.csv ./
scp lola@mini-obd.local:~/mini_obd/data/mini_obd.db ./
python scripts/04_analyse.py --session <N>
```

## Mode 2 — Live Watch (Hotspot or Wi-Fi connected)

Best for real-time diagnosis (especially P0100/MAF behavior).

Start interactive logger:

```bash
ssh lola@mini-obd.local
source ~/obd_env/bin/activate
python ~/mini_obd/scripts/03_obd_logger.py
```

Live output includes:
- MAF
- STFT
- LTFT
- RPM
- Coolant temp
- Real-time anomaly highlighting

For persistent remote run (disconnect-safe):

```bash
screen -S obd python ~/mini_obd/scripts/03_obd_logger.py
# detach: Ctrl+A, then D
# reattach: screen -r obd
```

---

### Post-Session Analysis (on Pi)

List sessions:

```bash
python ~/mini_obd/scripts/04_analyse.py --list
```

Analyze one session and generate plot:

```bash
python ~/mini_obd/scripts/04_analyse.py --session 3
```

Output plot location:
- `~/mini_obd/logs/`

Copy plot to laptop as needed with `scp`.

---

### Recommended Path for Current Fault (P0100 / DME 2B5 / 2B5F)

Use **Mode 2 (Live Watch)** first.  
Confirm whether:
- MAF is low at idle
- LTFT trends upward during operation

This gives immediate feedback for adaptation/power/ground investigation.