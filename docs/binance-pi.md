# Binance Setup

Binance is officially supported in this Freqtrade checkout.

## Config

Start from:

- `config_examples/config_binance_pi.example.json`

The example uses:

- `exchange.name = "binance"`
- `stake_currency = "USDT"`
- spot trading defaults

## Docker Compose

The compose file supports selecting config and strategy through environment variables:

```bash
FT_CONFIG=/freqtrade/user_data/config.binance.json
FT_STRATEGY=SampleStrategy
```

For a normal host-side run from the repository root:

```bash
FT_CONFIG=/freqtrade/user_data/config.binance.json docker compose up -d
```

## Raspberry Pi

If you use the Raspberry Pi systemd unit, add these environment variables to the service:

```ini
Environment=FT_BRANCH=stable
Environment=FT_CONFIG=/freqtrade/user_data/config.binance.json
Environment=FT_STRATEGY=SampleStrategy
```

Then place your filled-in config at `user_data/config.binance.json`.

## Notes

- Fill in your Binance API key and secret before starting the bot.
- Keep this in `dry_run` first.
- This repo still only contains the sample strategy unless you add your own strategy under `user_data/strategies`.
