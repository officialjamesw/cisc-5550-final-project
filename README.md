# Authenticated Todo App

This project extends a simple Flask todo list into a containerized, cloud-deployable web application. It includes a separate frontend service, backend API service, user authentication, user-specific tasks, due dates, reminder logic, Docker Compose support, and Kubernetes manifests for Google Kubernetes Engine.

For a more detailed write-up, see [REPORT.md](REPORT.md).

## Features

- User registration and login
- Password hashing
- Token-based authentication between frontend and backend
- User-specific task lists
- Due dates for tasks
- Reminder states for due soon and overdue tasks
- Backend audit logs for registration, login, and task actions
- Dockerized frontend and backend services
- Local multi-container testing with Docker Compose
- GKE deployment using Kubernetes Deployments, Services, Secret, and PersistentVolumeClaim

## Architecture Summary

```text
Browser
  -> Frontend Service
  -> Flask Frontend Container
  -> Backend Kubernetes/Compose Service
  -> Flask Backend API Container
  -> SQLite Database
```

In Docker Compose, the frontend reaches the backend at:

```text
http://backend:5001
```

In Kubernetes, the frontend reaches the backend through the internal service:

```text
http://todo-backend:5001
```

The public entry point in GKE is the `todo-frontend` LoadBalancer Service.

## Project Structure

```text
backend.py                   Backend API, authentication, tasks, reminders
todolist.py                  Frontend Flask app
templates/index.html         Main todo list page
templates/login.html         Login and registration page
Dockerfile                   Frontend container image
Dockerfile.backend           Backend container image
docker-compose.yml           Local multi-container setup
k8s/                         Kubernetes manifests for GKE
REPORT.md                    Detailed project report
```

## Run Locally with Docker Compose

From the project root:

```powershell
docker compose up --build
```

Open the app:

```text
http://localhost:5000
```

The backend API is available locally at:

```text
http://localhost:5001
```

Health check:

```text
http://localhost:5001/health
```

Backend logs include audit events for registration, login, task creation, task completion, and task deletion.

To stop the local containers:

```powershell
docker compose down
```

To also remove the local SQLite volume:

```powershell
docker compose down -v
```

## Deploy to GKE

These commands assume my own configuration:

- Google Cloud project: `infinite-alcove-485123-p2`
- Region: `us-central1`
- Location: `us-central1`
- GKE cluster: `todolist-cluster`
- Cluster mode: GKE Autopilot
- Artifact Registry repo: `todo-repo`

### 1. Set the Google Cloud Project

```powershell
gcloud config set project infinite-alcove-485123-p2
```

### 2. Enable Required APIs

```powershell
gcloud services enable container.googleapis.com artifactregistry.googleapis.com
```

### 3. Create Artifact Registry Repository

```powershell
gcloud artifacts repositories create todo-repo `
  --repository-format=docker `
  --location=us-central1 `
  --description="Todo app Docker images"
```

### 4. Configure Docker Authentication

```powershell
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### 5. Build Images

```powershell
docker build -t us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-frontend:latest .
```

```powershell
docker build -t us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-backend:latest -f Dockerfile.backend .
```

### 6. Push Images

```powershell
docker push us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-frontend:latest
```

```powershell
docker push us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-backend:latest
```

### 7. Connect kubectl to GKE

```powershell
gcloud container clusters get-credentials todolist-cluster --location us-central1
```

Verify the connection:

```powershell
kubectl get nodes
```

### 8. Apply Kubernetes Manifests

```powershell
kubectl apply -f k8s
```

### 9. Verify the Deployment

```powershell
kubectl get pods
kubectl get deployments
kubectl get services
kubectl get pvc
```

Check rollout status:

```powershell
kubectl rollout status deployment/todo-backend
kubectl rollout status deployment/todo-frontend
```

View backend audit logs:

```powershell
kubectl logs deployment/todo-backend
```

Example audit actions:

```text
audit action=register
audit action=login
audit action=login_failed
audit action=task_created
audit action=task_completed
audit action=task_deleted
```

### 10. Open the App

Get the frontend external IP:

```powershell
kubectl get service todo-frontend
```

Open:

```text
http://EXTERNAL-IP
```

## Kubernetes Resources

The `k8s` folder contains:

- `backend-deployment.yaml`
- `backend-service.yaml`
- `backend-pvc.yaml`
- `frontend-deployment.yaml`
- `frontend-service.yaml`
- `secret.yaml`

The backend service is internal-only using `ClusterIP`. The frontend service uses `LoadBalancer` so users can access the application from the internet.

## Troubleshooting

### `kubectl` Tries to Connect to `localhost:8080`

Example error:

```text
failed to download openapi: Get "http://localhost:8080/openapi/v2"
```

This means `kubectl` is not connected to a Kubernetes cluster yet.

Fix:

```powershell
gcloud container clusters get-credentials todolist-cluster --location us-central1
```

Then verify:

```powershell
kubectl get pods
```

### Cluster Not Found

Example error:

```text
No cluster named 'todo-cluster'
```

This means the command is using the wrong cluster name or location. List the available clusters:

```powershell
gcloud container clusters list
```

Use the exact `NAME` and `LOCATION` from that output:

```powershell
gcloud container clusters get-credentials todolist-cluster --location us-central1
```

### Wrong Zone vs Region

This project used a regional Autopilot cluster:

```text
todolist-cluster
us-central1
```

So this command is correct:

```powershell
gcloud container clusters get-credentials todolist-cluster --location us-central1
```

This command is incorrect for this cluster:

```powershell
gcloud container clusters get-credentials todolist-cluster --location us-central1-a
```

### `gke-gcloud-auth-plugin.exe not found`

Example error:

```text
executable gke-gcloud-auth-plugin.exe not found
```

Install the GKE authentication plugin:

```powershell
gcloud components install gke-gcloud-auth-plugin
```

Verify:

```powershell
gke-gcloud-auth-plugin.exe --version
```

If `gcloud` is not recognized, use the full path:

```powershell
& "C:\Users\jwils\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" components install gke-gcloud-auth-plugin
```

### `gcloud` Is Not Recognized

Example error:

```text
gcloud : The term 'gcloud' is not recognized
```

This means Google Cloud SDK is installed, but its `bin` folder is not on the Windows PATH.

Temporary fix for the current PowerShell window:

```powershell
$env:Path += ";C:\Users\jwils\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
```

Then test:

```powershell
gcloud --version
```

Permanent fix: add this folder to the Windows `Path` environment variable:

```text
C:\Users\jwils\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin
```

Then close and reopen PowerShell.

### Plugin Can Run, But `kubectl get nodes` Fails Because `gcloud` Is Missing

Example error:

```text
Failed to retrieve access token
exec: "gcloud": executable file not found in %PATH%
```

The plugin is installed, but it calls `gcloud` internally. Add Google Cloud SDK to PATH:

```powershell
$env:Path += ";C:\Users\jwils\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
```

Then retry:

```powershell
kubectl get pods
```

### Artifact Registry Push Is Unauthenticated

Example error:

```text
Unauthenticated requests do not have permission "artifactregistry.repositories.uploadArtifacts"
```

Authenticate Docker with Artifact Registry:

```powershell
gcloud auth login
gcloud config set project infinite-alcove-485123-p2
gcloud auth configure-docker us-central1-docker.pkg.dev
```

Verify the repository exists:

```powershell
gcloud artifacts repositories list --location=us-central1
```

Then retry:

```powershell
docker push us-central1-docker.pkg.dev/infinite-alcove-485123-p2/todo-repo/todo-frontend:latest
```

### Docker Image Built Locally But GKE Cannot Pull It

GKE cannot use an image that only exists on the local computer. The image must be pushed to Artifact Registry first.

Correct flow:

```text
docker build
docker push
kubectl apply
```

If the pods show image pull errors, check:

```powershell
kubectl get pods
kubectl describe pod POD_NAME
```

Make sure the image path in the deployment YAML exactly matches the pushed image path.

### Autopilot Node Pools Cannot Be Modified

Example error:

```text
Autopilot node pools cannot be accessed or modified.
```

This is normal for GKE Autopilot. Google manages the nodes automatically, so manual node pool commands are not needed.

Instead of checking or resizing node pools, check the workload:

```powershell
kubectl get pods
kubectl get deployments
kubectl get services
```

### `kubectl get nodes` Shows No Resources

For this project, the more important checks are:

```powershell
kubectl get pods
kubectl get deployments
kubectl get services
```

In Autopilot, Google manages node provisioning. Focus on whether the pods are scheduled and running.

### Pods Are Not Running

Check pod status:

```powershell
kubectl get pods
```

Describe the failing pod:

```powershell
kubectl describe pod POD_NAME
```

Check logs:

```powershell
kubectl logs deployment/todo-backend
kubectl logs deployment/todo-frontend
```

Common causes:

- Image path is wrong.
- Image was not pushed to Artifact Registry.
- Backend secret is missing.
- Container failed to start because of an application error.

### External IP Stays Pending

Check the frontend service:

```powershell
kubectl get service todo-frontend
```

If `EXTERNAL-IP` says `pending`, wait a few minutes and run the command again. Google Cloud may take time to provision the load balancer.

### Frontend Loads But Tasks Do Not Work

Check that the frontend has the correct backend service URL:

```yaml
env:
  - name: API_BASE
    value: http://todo-backend:5001
```

Then check backend logs:

```powershell
kubectl logs deployment/todo-backend
```

Check frontend logs:

```powershell
kubectl logs deployment/todo-frontend
```

### View User Activity Logs

The backend writes audit logs for major user actions:

```powershell
kubectl logs deployment/todo-backend
```

Useful actions to look for:

```text
audit action=register
audit action=login
audit action=login_failed
audit action=task_created
audit action=task_completed
audit action=task_deleted
```

These logs help verify that users are registering, logging in, and managing tasks.

### Stop Charges

Delete the cluster when finished:

```powershell
gcloud container clusters delete todolist-cluster --location us-central1
```

## Cleanup

Delete the GKE cluster to stop ongoing compute charges:

```powershell
gcloud container clusters delete todolist-cluster --location us-central1
```

Optional: delete the Artifact Registry repository if the images are no longer needed:

```powershell
gcloud artifacts repositories delete todo-repo --location us-central1
```
