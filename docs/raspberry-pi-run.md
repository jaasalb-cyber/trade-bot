# Raspberry Pi Run Flow

This setup updates the repository before starting the bot and then refreshes the Docker image.

## Files

- `scripts/run-on-raspberry-pi.sh`
- `scripts/freqtrade-raspberry-pi.service`

## Pi Setup

Clone this repository to the Raspberry Pi, for example to `/home/pi/trade-bot`.

Create and configure `user_data/config.json` before enabling the service.

Make the startup script executable:

```bash
chmod +x /home/pi/trade-bot/scripts/run-on-raspberry-pi.sh
```

Install the systemd unit:

```bash
sudo cp /home/pi/trade-bot/scripts/freqtrade-raspberry-pi.service /etc/systemd/system/freqtrade.service
sudo systemctl daemon-reload
sudo systemctl enable freqtrade.service
sudo systemctl start freqtrade.service
```

## Behavior

When the service starts it will:

1. `git pull --ff-only origin stable`
2. `docker compose pull`
3. `docker compose up -d`

To stop the bot:

```bash
sudo systemctl stop freqtrade.service
```

To inspect logs:

```bash
sudo journalctl -u freqtrade.service -f
docker compose logs -f
```

## Notes

- If your Pi user is not `pi`, update `User`, `Group`, `WorkingDirectory`, and `ExecStart` in the service file.
- If you want a different git branch, change `Environment=FT_BRANCH=stable`.
- The service uses Docker Compose from the repository root, so it will pick up `docker-compose.yml` automatically.
