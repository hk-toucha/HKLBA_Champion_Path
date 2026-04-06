# Champion Path Docker Setup

## Quick start (docker compose)

```bash
cd docker

# Create host directories for persistent data
sudo mkdir -p /var/champion_path/archive /var/www/championpath/data

# (Optional) Copy .env.example to .env and edit the paths
cp .env.example .env

# Build and start (detached)
docker compose up -d --build

# View logs
docker compose logs -f

# Stop and remove
docker compose down

# Rebuild after code changes
docker compose up -d --build
```

## Manual docker commands (legacy)

### Stop, purge, and remove
```bash
docker stop champion_path_job
docker container prune -f
docker image rm champion_path
```

### Build
```bash
docker build -t champion_path .
```

### Run
```bash
docker run -d --restart=always --name champion_path_job \
  -v /var/champion_path/archive:/app/archive \
  -v /var/www/championpath/data:/app/local_data \
  champion_path
```

### Shell into container
```bash
docker exec -it champion_path_job /bin/bash
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ARCHIVE_HOST_PATH` | `/var/champion_path/archive` | Host path for fixture PDF archive |
| `DATA_HOST_PATH` | `/var/www/championpath/data` | Host path for processed `.gz` data files |

## What the container does

A cron job runs `ExtractLBA_Files.py` every 30 minutes (at :10 and :40)
during business hours (10:00-19:00, Mon-Fri HKT). It:

1. Scrapes the LBA website for fixture PDFs
2. Downloads new/updated PDFs to `/app/archive`
3. Parses each PDF with `fixture_parser.py`
4. Writes compressed JSON data to `/app/local_data`
