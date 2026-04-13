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

## 🛠️ Tech Stack

**Frontend:**
- React (Vite)
- Tailwind CSS
- Framer Motion

**Backend:**
- Python 3.10
- FastAPI
- Endee Vector Database
- LangChain Google GenAI
- BeautifulSoup4 & Newspaper3k

## 🚀 Getting Started (Docker Compose)

The easiest and recommended way to run the application is to use the integrated **Docker Compose** stack from the project root. This spins up the Endee Vector Database, the Python API, and the React UI fully linked together.

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

### 1. Build and Run the Stack
Open a terminal in the **root** folder of this repository (where the main `docker-compose.yml` is located) and run:

```bash
docker-compose up -d --build
```

*Note: The first time you run this, it will download necessary CUDA/PyTorch elements and will take some time. Later runs are instantaneous!*

### 2. Access the Application
Once the containers are successfully running, access the portals at:

- **Frontend Application UI:** [http://localhost:5173](http://localhost:5173)
- **Backend API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Endee Vector Database API:** [http://localhost:8080/docs](http://localhost:8080/docs)

To stop the application cleanly, run `docker-compose down`.

## 🤝 Architecture

- **`main.py`**: The FastAPI entry point, defining routes and orchestrating database/inference flow.
- **`rag_pipeline.py` & `hybrid_rag.py`**: Interacts with the Endee Local Vector database and external Search APIs/LLMs to generate trustworthy analysis context.
- **`scraper.py`**: Contains robust logic to strip noise from URLs to extract actual article content using Newspaper3k.
- **`App.jsx`**: The main React component rendering the dynamic user interface.

## 📝 License

This project is licensed under the MIT License.
