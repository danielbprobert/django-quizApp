# 🧠 Quiz App

A lightweight Django web application for running interactive team quizzes.

Players join with a unique 6-digit code, choose a fun nickname and avatar, and compete through timed questions (text or image-based) with live scoring and results.

---

## 📦 Release Version

**Version:** 1.0.0  
**Date:** October 2025  
**Status:** Internal release for testing and team demos

---

## 🚀 Features

- 🎯 Host-controlled quiz sessions (start quizzes from the admin panel)
- 👥 Live lobby showing all connected players
- ⏱️ 15-second timer per question, automatic transitions
- 🧩 Support for text and/or image questions and answers (1 correct of 4)
- 🏆 Leaderboard with score and accuracy percentage
- 😄 Random silly name and avatar on join
- 🔒 Secured admin area (custom URL, optional IP allowlist)
- 🧰 Simple to deploy and update via Git pulls

---

## 🧰 Tech Stack

- **Backend:** Django 5 + Channels (InMemory backend)
- **Frontend:** Pico.css + HTMX for reactive updates
- **Database:** SQLite 3
- **Deployment:** Ubuntu 22 LTS (AWS EC2), Gunicorn + Nginx
- **Python:** 3.11+

---

## ⚙️ Local Development Setup

### Prerequisites
- Python ≥ 3.11  
- Git  
- VS Code (recommended)

### 1️⃣ Clone & Install
```bash
git clone https://github.com/<yourname>/quiz-app.git
cd quiz-app
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2️⃣ Environment Variables
Create a `.env` file in the project root:

```ini
DJANGO_SECRET_KEY=dev-secret-change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1,http://localhost
DJANGO_ADMIN_URL=admin/
DJANGO_ADMIN_IPS=127.0.0.1
```

### 3️⃣ Run the app
```bash
python manage.py migrate
python manage.py runserver
```

Visit → [http://127.0.0.1:8000](http://127.0.0.1:8000)

Admin → [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

*(The admin URL comes from your `.env` file.)*

---

## ☁️ AWS Deployment

### 1️⃣ Launch an EC2 instance
- OS: **Ubuntu 22.04 LTS**
- Type: **t3.small** or **t3.micro**
- Inbound rules: allow **22 (SSH)**, **80 (HTTP)**, **443 (HTTPS)**

SSH into it:
```bash
ssh -i your-key.pem ubuntu@<your-ec2-public-ip>
```

### 2️⃣ Install dependencies
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git nginx certbot python3-certbot-nginx
```

### 3️⃣ Clone and set up
```bash
cd /home/ubuntu
git clone https://github.com/danielbprobert/django-quizApp.git
cd quiz-app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

### 4️⃣ Environment file on the server
```ini
DJANGO_SECRET_KEY=super-long-random-key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-domain.com,<your-ec2-public-ip>
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://<your-ec2-public-ip>
DJANGO_ADMIN_URL=secure-admin-url-control/
```

### 5️⃣ Gunicorn service
Create `/etc/systemd/system/quizapp.service`:
```ini
[Unit]
Description=Gunicorn for quiz app
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/quiz-app
EnvironmentFile=/home/ubuntu/quiz-app/.env
ExecStart=/home/ubuntu/quiz-app/venv/bin/gunicorn --workers 1 --bind unix:/home/ubuntu/quiz-app/quizapp.sock config.wsgi:application

[Install]
WantedBy=multi-user.target
```
Then:
```bash
sudo systemctl daemon-reload
sudo systemctl start quizapp
sudo systemctl enable quizapp
```

### 6️⃣ Nginx configuration
Create `/etc/nginx/sites-available/quizapp`:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location = /favicon.ico { access_log off; log_not_found off; }

    location /static/ { alias /home/ubuntu/quiz-app/staticfiles/; }
    location /media/  { alias /home/ubuntu/quiz-app/media/; }

    location / {
        include proxy_params;
        proxy_pass http://unix:/home/ubuntu/quiz-app/quizapp.sock;
    }
}
```
Enable and restart:
```bash
sudo ln -s /etc/nginx/sites-available/quizapp /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

### 7️⃣ Enable HTTPS
```bash
sudo certbot --nginx -d your-domain.com
```

Once SSL is working, uncomment HSTS settings in `config/settings.py`:
```python
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

---

## 🧑‍💻 Deployment Workflow (Git Pull Updates)

When pushing updates from local to the server:

```bash
ssh -i your-key.pem ubuntu@<your-ec2-public-ip>
cd ~/quiz-app
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart quizapp
```

---

## 📁 Project Structure

```
quiz-app/
│
├── config/             # Django config, settings, URLs, middleware
├── quiz/               # Core quiz logic, models, views, templates
├── static/             # Custom CSS and static assets
├── templates/          # Base templates and shared components
├── manage.py
└── .env
```

---

## 🔒 Security Notes

- Admin URL and IP restrictions are controlled via `.env`
- HTTPS enforced in production (`DEBUG=False`)
- HSTS activated after SSL validation
- No Redis or Postgres required
- SQLite database located at `BASE_DIR/db.sqlite3`
- In-memory Channels layer (single Gunicorn worker recommended)

---

## 📜 License

MIT License  
© 2025 Daniel Probert — Internal Use / Demo Project