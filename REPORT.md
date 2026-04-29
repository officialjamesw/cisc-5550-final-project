# Todo Web Application Modernization Report

## 1. Project Overview

This project began as a simple todo list web application. I extended it into a multi-service web application with user authentication, user-specific task management, due dates, reminder logic, Docker containerization, and Kubernetes deployment on Google Kubernetes Engine.

The final application includes:

- A Flask frontend service for the user interface.
- A Flask backend API service for authentication and task management.
- SQLite persistence for users and tasks.
- Docker images for both frontend and backend services.
- Docker Compose support for local multi-container testing.
- Kubernetes Deployments and Services for GKE cloud deployment.
- Google Artifact Registry for storing container images.

## 2. Original Application

The original application was a basic Flask frontend that displayed a todo list and sent requests to a hard-coded external backend API.

The original setup had several limitations:

- No user accounts or login system.
- No private task lists per user.
- No backend code included in the project repository.
- No local multi-container deployment setup.
- No Kubernetes cloud deployment architecture.
- The frontend depended on a fixed external API address.

## 3. New Architecture

The updated application uses a two-service architecture.

```text
User Browser
    |
    v
GKE LoadBalancer Service
    |
    v
Frontend Flask Container
    |
    v
Backend Kubernetes Service
    |
    v
Backend Flask API Container
    |
    v
SQLite Database on Persistent Volume
```

The frontend and backend are separated into different containers. The frontend handles browser pages, login forms, task forms, and user sessions. The backend handles users, passwords, authentication tokens, tasks, due dates, and reminders.

## 4. Features Added

### User Authentication

I added registration and login functionality. Users can create accounts and log in with a username and password.

Passwords are not stored as plain text. The backend hashes passwords using Werkzeug password hashing before storing them in SQLite.

### User-Specific Task Management

Tasks are now connected to a specific user account. After logging in, each user only sees and manages their own tasks.

This required changing the task API so every task request must include a valid authentication token.

### Due Dates

Tasks now support due dates. The frontend uses a date/time input, and the backend stores the due date with the task.

### Reminder Logic

The backend calculates reminder status based on the due date.

Reminder states include:

- `none`: the task is not close to the due date.
- `due_soon`: the task is due within the reminder window.
- `overdue`: the due date has already passed.

The frontend displays reminder information so users can quickly see which tasks need attention.

## 5. Backend API

I added a new backend service in `backend.py`.

Important backend endpoints include:

```text
POST /api/register
POST /api/login
GET  /api/tasks
POST /api/tasks
POST /api/tasks/<task_id>/done
DELETE /api/tasks/<task_id>
GET  /api/reminders
GET  /health
```

The backend uses bearer-token authentication. After login or registration, the backend returns a token. The frontend sends that token back to the backend when requesting, creating, completing, or deleting tasks.

## 6. Frontend Updates

The frontend in `todolist.py` was updated so it no longer talks to a hard-coded external IP address.

Instead, it reads the backend URL from an environment variable:

```text
API_BASE
```

In Docker Compose and Kubernetes, this value points to the backend service:

```text
http://backend:5001
```

for Docker Compose, and:

```text
http://todo-backend:5001
```

for Kubernetes.

I also added:

- Login page.
- Registration page.
- Logout route.
- Task creation form with due date.
- Reminder display.
- POST-based complete and delete actions.

## 7. Docker Containerization

I created separate Docker images for the frontend and backend.

Frontend:

```text
Dockerfile
```

Backend:

```text
Dockerfile.backend
```

Both services install Python dependencies from `requirements.txt` and run using Gunicorn.

## 8. Docker Compose Local Testing

I added `docker-compose.yml` so the application can be tested locally as two containers.

The Docker Compose setup includes:

- `frontend` service on port `5000`.
- `backend` service on port `5001`.
- A Docker volume for backend SQLite data.
- Environment variables for service-to-service communication.

Local command:

```powershell
docker compose up --build
```

Then the app can be opened at:

```text
http://localhost:5000
```

## 9. Google Artifact Registry

For GKE deployment, the Docker images must be stored somewhere GKE can access them.

I used Google Artifact Registry.

Image names:

```text
us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-frontend:latest
us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-backend:latest
```

The images were built locally and pushed to Artifact Registry.

## 10. Kubernetes and GKE Deployment

I added Kubernetes manifests in the `k8s` folder.

The Kubernetes setup includes:

- Backend Deployment.
- Backend Service.
- Frontend Deployment.
- Frontend LoadBalancer Service.
- Secret for the application secret key.
- PersistentVolumeClaim for backend SQLite storage.

The frontend Service is a `LoadBalancer`, which gives the application a public external IP address on Google Cloud.

The backend Service is a `ClusterIP`, which means it is only reachable inside the Kubernetes cluster. This is more secure because users do not access the backend directly.

## 11. Deployment Steps

### Step 1: Set the Google Cloud Project

```powershell
gcloud config set project infinite-alcove-485123-p2
```

### Step 2: Enable Required APIs

```powershell
gcloud services enable container.googleapis.com artifactregistry.googleapis.com
```

### Step 3: Create Artifact Registry Repository

```powershell
gcloud artifacts repositories create todo-repo `
  --repository-format=docker `
  --location=us-central1 `
  --description="Todo app Docker images"
```

### Step 4: Configure Docker Authentication

```powershell
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### Step 5: Build Docker Images

```powershell
docker build -t us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-frontend:latest .
```

```powershell
docker build -t us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-backend:latest -f Dockerfile.backend .
```

### Step 6: Push Images to Artifact Registry

```powershell
docker push us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-frontend:latest
```

```powershell
docker push us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-backend:latest
```

### Step 7: Create or Connect to GKE Cluster

```powershell
gcloud container clusters get-credentials todo-cluster --location us-central1-a
```

### Step 8: Verify Kubernetes Connection

```powershell
kubectl get nodes
```

### Step 9: Deploy Kubernetes Manifests

```powershell
kubectl apply -f k8s
```

### Step 10: Verify the Deployment

```powershell
kubectl get pods
kubectl get deployments
kubectl get services
kubectl get pvc
```

### Step 11: Open the Application

```powershell
kubectl get service todo-frontend
```

The external IP from the `todo-frontend` service is the public URL for the application.

## 12. Verification Commands

Useful commands for checking the deployment:

```powershell
kubectl get pods
kubectl get services
kubectl rollout status deployment/todo-backend
kubectl rollout status deployment/todo-frontend
kubectl logs deployment/todo-backend
kubectl logs deployment/todo-frontend
```

The backend can also be tested with the health endpoint from inside the cluster or by port forwarding:

```powershell
kubectl port-forward service/todo-backend 5001:5001
```

Then open:

```text
http://localhost:5001/health
```

## 13. Technologies Explored

This project experimented with several technologies beyond the original application:

- Flask backend API development.
- Password hashing.
- Token-based authentication.
- User-specific data isolation.
- SQLite persistence.
- Docker images.
- Docker Compose multi-container networking.
- Google Artifact Registry.
- Google Kubernetes Engine.
- Kubernetes Deployments.
- Kubernetes Services.
- Kubernetes Secrets.
- Kubernetes PersistentVolumeClaims.
- Public cloud LoadBalancer deployment.

## 14. What I Learned

This project helped me understand how a web application moves from a simple local Flask app to a cloud-deployed containerized system.

The most important lesson was that Kubernetes does not directly run source code from a repository. Instead, the code is packaged into Docker images, pushed to a registry, and then pulled by Kubernetes when creating containers.

I also learned how frontend and backend services communicate inside a containerized environment. In local Docker Compose, the frontend talks to the backend using the Compose service name. In Kubernetes, the frontend talks to the backend using the Kubernetes Service name.

## 15. Conclusion

The completed project is now more advanced than the original todo list application. It supports authentication, private user task lists, due dates, reminders, local container testing, and cloud deployment on GKE.

This demonstrates a clear understanding of the application components, how they communicate, and how modern container-based deployment works.
