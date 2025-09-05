#!/bin/bash
PORT=${PORT:-8000}
uvicorn src.main:app --host 0.0.0.0 --port $PORT
