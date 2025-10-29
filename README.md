# GCIDE Dictionary Explorer

A web application for exploring word relationships in the GNU GCIDE dictionary. Words are linked through their definitions, creating an interconnected graph of language.

## Features

- **Word Lookup**: Search for any word and view its definition
- **Interactive Definitions**: Words within definitions are clickable links to explore related words
- **Graph Statistics**: View interesting graph properties like:
  - Total words and connections
  - Most referenced words
  - Circular definition dependencies
  - Degree distributions
- **Fast Performance**: Optimized database queries and indexing for quick lookups
- **Modern UI**: Clean, responsive interface built with React

## Architecture

The application is built with a modular architecture for easy deployment:

- **Backend**: FastAPI (Python) with async SQLite database
- **Frontend**: React with Vite
- **Graph Analysis**: NetworkX for computing graph statistics
- **Deployment**: Docker containers with docker-compose

## Setup

### Prerequisites

- Python 3.12+
- Node.js 20+ (for frontend development)
- Docker and Docker Compose (for containerized deployment)

### Local Development

1. **Backend Setup**:
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Set environment variable for automatic download (optional)
   export GCIDE_URL="https://example.com/gcide-0.54.zip"
   
   # Run the API server (will auto-download GCIDE data if GCIDE_URL is set)
   uvicorn app.main:app --reload --port 8000
   ```
   
   **Note**: The application will automatically check for GCIDE dictionary data on startup.
   If the database doesn't exist or is empty, and `GCIDE_URL` environment variable is set,
   it will automatically download and process the dictionary.

2. **Frontend Setup**:
   ```bash
   cd client
   npm install
   npm run dev
   ```

3. **Access the application**:
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Docker Deployment

```bash
# Build and run all services
docker-compose up --build

# Or run in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

The application will be available at:
- Frontend: http://localhost:3000
- API: http://localhost:8000

## Getting GCIDE Dictionary Data

The application automatically handles GCIDE dictionary data:

### Automatic Download (Recommended)

Set the `GCIDE_URL` environment variable to the URL of the GCIDE zip file:

```bash
export GCIDE_URL="https://example.com/gcide-0.54.zip"
```

When you start the application, it will:
1. Check if the database exists and has data
2. If not, download the zip file from the URL
3. Extract and process the dictionary files
4. Load them into the SQLite database

The application will start even if the download fails, but dictionary features won't work until data is loaded.

### Manual Processing

Alternatively, you can manually download and process the dictionary:

1. Download GCIDE dictionary files from: https://www.gnu.org/software/gcide/
2. Place XML/text files in `data/gcide_raw/` directory
3. Run the processing script:

```bash
python -m app.data.process_gcide --data-dir data/gcide_raw --db-path data/gcide.db
```

Or use the script with download URL:

```bash
python -m app.data.process_gcide --download-url "https://example.com/gcide-0.54.zip"
```


## Project Structure

```
xNillio/
├── app/                    # Backend API
│   ├── main.py            # FastAPI app entry point
│   ├── api/
│   │   └── routes/        # API endpoints
│   ├── services/          # Business logic
│   └── data/              # Data processing scripts
├── client/                 # Frontend React app
│   ├── src/
│   │   ├── components/    # React components
│   │   └── App.jsx        # Main app component
│   └── package.json
├── data/                   # Data directory
│   ├── gcide_raw/         # Raw GCIDE files (not in git)
│   └── gcide.db           # Processed SQLite database
├── docker/                 # Docker configurations
├── docker-compose.yml      # Docker Compose setup
└── requirements.txt        # Python dependencies
```

## Cloud Deployment

The application is designed for easy cloud deployment:

1. **Container Registry**: Build and push Docker images
2. **Database**: Use managed PostgreSQL/MySQL instead of SQLite for production
3. **Environment Variables**: Configure via environment variables:
   - `DATABASE_PATH` - Database file path
   - `API_HOST` - API host address
   - `API_PORT` - API port

Example for AWS/GCP/Azure:
- Use container orchestration (ECS, Cloud Run, Container Instances)
- Connect to managed database service
- Use load balancer for API
- CDN for frontend static assets
