# AI Fake News Detector

A professional, full-stack application designed to analyze news articles (via URL or raw text) and determine their authenticity using natural language processing heuristics, coupled with the blazing fast **Endee Vector Database** for Retrieval-Augmented Generation (RAG).

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![React](https://img.shields.io/badge/react-%2320232a.svg?style=flat&logo=react&logoColor=%2361DAFB)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker)

## ✨ Features

- **Real-Time Analysis**: Instantly evaluate the trustworthiness of web and text content.
- **RAG Powered Verification**: Uses Google Generative AI combined with Endee Vector database for deep contextual verification.
- **Persistent History**: Automatically saves analysis results to a local database and displays a "Recent Analyses" timeline on the dashboard.
- **Premium UI/UX**: Built with React, TailwindCSS, and Framer Motion for a stunning dark mode interface.

## 🛠️ Architecture & Tech Stack

This project uses a modern microservices architecture running via Docker Compose:

1. **Frontend (React + Vite)**: Handles the modern user interface and timeline. (Runs on port `5173`)
2. **Backend (Python FastAPI)**: Handles web scraping (via `newspaper3k` & `BeautifulSoup`), semantic processing, and LLM verification. (Runs on port `8000`)
3. **Vector Database (Endee OSS)**: A high-performance local vector database customized for ultra-fast RAG vector retrieval. (Runs on port `8080`)

## 🚀 Getting Started

The easiest and recommended way to run the application is to use the integrated **Docker Compose** stack from the project root. This spins up the Endee Vector Database, the Python API, and the React UI fully linked together.

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

### 1. Build and Run the Stack
Open a terminal in the root folder of this repository (where this `docker-compose.yml` is located) and run:

```bash
docker-compose up -d --build
```

*Note: The very first time you run this, it will download necessary CUDA/PyTorch elements and will take some time. Every subsequent run will be nearly instantaneous!*

### 2. Access the Application
Once the containers are successfully running, you can access the completely integrated suite at:

- **Frontend Application UI:** [http://localhost:5173](http://localhost:5173)
- **Backend API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Endee Vector Database API:** [http://localhost:8080/docs](http://localhost:8080/docs)

To shut down the application cleanly, just run:
```bash
docker-compose down
```

## 📡 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | API Health Check |
| `GET` | `/history` | Fetch the most recent analysis checks |
| `POST` | `/analyze` | Submit text or URL for fake news analysis |

## 📝 License

This project is licensed under the MIT License.
