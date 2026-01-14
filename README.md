# Lumina Backend

FastAPI backend service for Lumina application.

## Quick Start

### 1. Clone and Setup Environment

```bash
# Install dependencies
uv sync

# Copy environment template
cp .env.example .env  # Edit with your configuration
```

### 2. Start the Application (Auto-Initialize)

The application will automatically initialize the database on startup:

```bash
uv run uvicorn app.main:app --reload
```

**What happens automatically:**
- ✓ Checks if database exists, creates it if missing
- ✓ Creates all tables based on SQLModel definitions
- ✓ No manual database setup required!

**Configuration**: Edit `DATABASE_URL` in `.env` file

Alternatively, if you prefer manual setup:

```bash
uv run python scripts/setup.py
```

### 3. Access the Application

```bash
uv run uvicorn main:app --reload
```

Visit http://localhost:8000/docs for interactive API documentation.

## API Endpoints

See [DATABASE.md](DATABASE.md) for detailed API documentation.

## Project Structure

```
app/
├── core/
│   ├── config.py          # Application configuration
│   └── database.py        # Database engine and session
├── models/
│   └── user.py            # SQLModel models
└── api/routes/
    └── users.py           # User routes
scripts/
└── setup.sh               # Setup script for initialization
```

## Data Migration

### Compress data directory

```bash
# tar.gz (recommended)
tar -czvf data.tar.gz data/

# tar.zst (faster, smaller, requires zstd)
tar -I zstd -cvf data.tar.zst data/

# zip
zip -r data.zip data/
```

### Upload to server

```bash
# scp
scp data.tar.gz user@server:/path/to/destination/

# rsync (supports resume)
rsync -avzP data.tar.gz user@server:/path/to/destination/
```

### Extract on server

```bash
# tar.gz
tar -xzvf data.tar.gz

# tar.zst
tar -I zstd -xvf data.tar.zst

# zip
unzip data.zip
```
