#!/bin/bash
cd "$(dirname "$0")/.."

# Function to kill child processes on exit
cleanup() {
    echo ""
    echo "Stopping Phantom services..."
    # Kill the process groups to ensure all children are dead
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null
    fi
    echo "Services stopped."
    exit
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

echo "Starting Phantom Backend..."
if command -v uv &> /dev/null; then
    uv run phantom-backend &
    BACKEND_PID=$!
else
    echo "Error: 'uv' command not found. Please install uv first."
    exit 1
fi

echo "Starting Phantom Frontend..."
if [ -d "gui" ]; then
    cd gui
    if command -v npm &> /dev/null; then
        npm run dev &
        FRONTEND_PID=$!
    else
        echo "Error: 'npm' command not found. Please install node.js/npm first."
        cd ..
        kill $BACKEND_PID 2>/dev/null
        exit 1
    fi
    cd ..
else
    echo "Error: 'gui' directory not found."
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

echo ""
echo "Both services are running in the background."
echo "- Backend PID: $BACKEND_PID"
echo "- Frontend PID: $FRONTEND_PID"
echo ""
echo "Press Ctrl+C to stop both services."

# Wait for background processes to finish (optional, but keeps script alive)
wait $BACKEND_PID $FRONTEND_PID
