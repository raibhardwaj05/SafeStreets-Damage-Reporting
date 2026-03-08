# 🚧 SafeStreets – AI Road Damage Detection & Infrastructure Monitoring System

![Python](https://img.shields.io/badge/Python-3.10-blue)
![Flask](https://img.shields.io/badge/Framework-Flask-black)
![YOLO](https://img.shields.io/badge/AI-YOLOv8-red)
![OpenCV](https://img.shields.io/badge/ComputerVision-OpenCV-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

SafeStreets is an *AI-powered road infrastructure monitoring platform* designed to detect, report, and manage road damage efficiently.

The system integrates *computer vision, geolocation, and web technologies* to allow citizens to report infrastructure damage while enabling municipal authorities to verify and manage repairs through a centralized dashboard.

⚠️ *Important:*
The entire system — including the *AI detection model, backend APIs, frontend interfaces, and workflow logic — was developed from scratch by our team. No pre-built solutions or cloned systems were used.*

The AI model was *custom-trained by our team using YOLO architecture* to detect:

* *Potholes*
* *Road cracks*

---

## 📑 Table of Contents

- [System Architecture](#-system-architecture)
- [Features](#-features)
- [AI Detection Pipeline](#-ai-detection-pipeline)
- [Model Training](#-model-training)
- [Tech Stack](#-tech-stack)
- [Model File](#-model-file)
- [Installation](#-installation)
- [Run Locally](#️-run-locally)
- [Usage](#️-usage)
- [Project Structure](#-project-structure)
- [Roadmap](#️-roadmap)
- [License](#-license)
- [Authors](#-authors)

---

# 🧠 System Architecture

```
Citizen Device
(Image / Video / Camera)
        │
        ▼
Frontend Web Interface
(HTML, CSS, JavaScript)
        │
        ▼
Flask Backend API
(Authentication + Report Handling)
        │
        ├──────────────► SQLite Databases
        │                (Users, Reports, Work Notices, Logs)
        │
        ▼
AI Detection Service
(YOLO + OpenCV)
        │
        ▼
Detection Results
(Damage Type + Severity)
        │
        ▼
Officer Dashboard
(Verification, Work Assignment, Analytics)
```


---

# ✨ Features

## 👤 Citizen Portal

* Citizen registration and authentication
* Upload images or videos of road damage
* Real-time detection using device camera
* Automatic GPS location capture
* AI-based damage classification
* Submit infrastructure damage reports
* Track report progress and status
* View reporting history

---

## 🏛️ Official Portal

* Secure officer login portal
* Infrastructure monitoring dashboard
* Review citizen-submitted damage reports
* Verify or reject reports
* Upload official work notices
* Assign repair tasks
* Download report documentation (PDF)
* Monitor repair progress

---

## 📊 Analytics Dashboard

* Total infrastructure reports
* Completed repair statistics
* Average repair time
* Municipal spending overview
* Contractor performance metrics
* Road health index by sector

---

# 🤖 AI Detection Pipeline

```
Road Image / Video Frame
        │
        ▼
Image Preprocessing
(OpenCV)
        │
        ▼
YOLO Detection Model
(Custom trained by our team)
        │
        ▼
Object Detection
(Pothole / Crack)
        │
        ▼
Confidence Score Calculation
        │
        ▼
Severity Classification
(High / Medium / Low)
        │
        ▼
Damage Report Generated
```


---

# 🏋️ Model Training

The YOLO detection model used in this system was **trained by our team from scratch** using a custom road damage dataset.

The model currently detects:

- Potholes
- Road cracks

The trained model file is stored as:

```
model/best.pt
```

This ensures the entire AI pipeline in this project is **fully custom-built and not dependent on third-party pre-trained solutions for this task.**

---

# 🧰 Tech Stack

## Backend

* Python
* Flask
* SQLAlchemy
* Flask-JWT Authentication
* OpenCV
* Ultralytics YOLO

## Frontend

* HTML5
* CSS3
* JavaScript

## Database

* SQLite

## Additional Tools

* pdfplumber (PDF processing)
* Geolocation API
* REST APIs

---

# 🧠 Model File

Place the trained YOLO model inside the `model` folder before running the system.

```
model/
 └── best.pt
```

This model was **trained by our team from scratch** to detect road damage types such as potholes and cracks.

---

# 📦 Installation

Clone the repository


```bash
git clone https://github.com/Rehan-Aditya8/rdd2-c.git
cd rdd2-c
```


Create virtual environment


```bash
python -m venv venv
```


Activate environment

### Windows
```bash
venv\Scripts\activate
```

### Mac / Linux
```bash
source venv/bin/activate
```


Install dependencies


```bash
pip install -r backend/requirements.txt
```


---

# ▶️ Run Locally

Start the backend server

```bash
cd backend
python run.py
```

The server will start at:

```
http://127.0.0.1:5000
```


Open the link in a browser to access the platform.

---

# ⚙️ Usage

## Citizen Workflow

1. Citizen registers or logs in.
2. Uploads an image or video of road damage.
3. AI model detects pothole or crack.
4. GPS coordinates are captured automatically.
5. Citizen submits report.
6. Report status becomes *Pending Review*.

---

## Officer Workflow

1. Officer logs in through the official portal.
2. Dashboard displays report statistics.
3. Officers review submitted reports.
4. Valid reports are verified.
5. Work notices are created.
6. Contractors are assigned for repairs.
7. Repair progress is monitored through analytics.

---

# 📂 Project Structure

```
rdd2-c
│
├── backend
│   ├── app
│   ├── instance
│   ├── uploads
│   │   ├── images
│   │   ├── temp
│   │   └── work_notices
│   ├── config.py
│   ├── run.py
│   └── requirements.txt
│
├── citizen
│   ├── scripts
│   ├── styles
│   ├── dashboard.html
│   ├── dashcam.html
│   ├── map.html
│   └── report-damage.html
│
├── official
│   ├── scripts
│   ├── styles
│   ├── dashboard.html
│   ├── reports.html
│   └── analytics.html
│
├── shared
│   ├── auth.js
│   ├── navigation.js
│   └── modal.js
│
├── model
│   └── best.pt
│
└── notices
    ├── Notice.pdf
    ├── Notice2.pdf
    └── Notice3.pdf
```

---

# 🛣️ Roadmap

Future improvements planned:

* Support additional road damage types
* Mobile application for citizen reporting
* Integration with smart city sensors
* Automated contractor assignment
* Real-time monitoring using municipal vehicles
* Cloud deployment for smart city scalability

---

# 📜 License

This project is developed for *educational, research, and civic technology purposes*.

---

# 👨‍💻 Authors

SafeStreets Development Team

### Contributors

- Bhardwaj Rai  
- Rehan Aditya  
- Rudra Pratap Sahoo  
- Aayush Ram
