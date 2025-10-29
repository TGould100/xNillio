#!/bin/bash

# Quick start script for GCIDE Dictionary Explorer

echo "GCIDE Dictionary Explorer - Quick Start"
echo "========================================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install -q -r requirements.txt

# Check if database exists
if [ ! -f "data/gcide.db" ]; then
    echo ""
    echo "WARNING: Dictionary database not found!"
    echo "Please download GCIDE dictionary files and run:"
    echo "  python -m app.data.process_gcide --data-dir data/gcide_raw --db-path data/gcide.db"
    echo ""
    echo "You can download GCIDE from: https://www.gnu.org/software/gcide/"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Start backend
echo "Starting backend API server..."
echo "API will be available at http://localhost:8000"
echo "API docs at http://localhost:8000/docs"
echo ""
uvicorn app.main:app --reload --port 8000 &

BACKEND_PID=$!

# Wait a moment for backend to start
sleep 2

# Check if frontend dependencies are installed
if [ ! -d "client/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd client && npm install && cd ..
fi

# Start frontend
echo "Starting frontend dev server..."
echo "Frontend will be available at http://localhost:3000"
echo ""
cd client && npm run dev &

FRONTEND_PID=$!

echo ""
echo "========================================"
echo "Application is running!"
echo "Press Ctrl+C to stop all services"
echo "========================================"

# Wait for user interrupt
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait

