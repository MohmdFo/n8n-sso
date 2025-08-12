# Dify SSO Gateway

Dify SSO Gateway is a FastAPI-based Single Sign-On (SSO) service that integrates with [Casdoor](https://casdoor.org/) to provide OAuth-based authentication and token management in a Dify-like format. The gateway handles user login, signup, and callback flows while dynamically constructing callback URLs and generating both access and refresh tokens. It also includes health-check endpoints, API versioning, and logging to ensure a scalable and maintainable authentication solution.

---

## Table of Contents

- [Dify SSO Gateway](#dify-sso-gateway)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Purpose and Issues Addressed](#purpose-and-issues-addressed)
    - [What Problems Are Solved?](#what-problems-are-solved)
  - [Architecture and Project Structure](#architecture-and-project-structure)
    - [Description of Key Components](#description-of-key-components)
  - [Features](#features)
  - [Installation and Setup](#installation-and-setup)
    - [Prerequisites](#prerequisites)
    - [Dependencies](#dependencies)
  - [Environment Configuration](#environment-configuration)
  - [Usage](#usage)
    - [Running in Development Mode](#running-in-development-mode)
    - [Running in Production Mode](#running-in-production-mode)
    - [CLI Commands](#cli-commands)
  - [How It Works](#how-it-works)
  - [Logging and Error Handling](#logging-and-error-handling)
  - [API Endpoints](#api-endpoints)
    - [Authentication Endpoints (`/v1/auth/`)](#authentication-endpoints-v1auth)
    - [Core Endpoints (`/v1/`)](#core-endpoints-v1)
  - [Additional Considerations](#additional-considerations)
  - [License](#license)

---

## Overview

The **Dify SSO Gateway** is built using FastAPI and modularizes authentication into distinct components. It leverages:

- **OAuth and Casdoor Integration:** Authenticate users via Casdoor with dynamic callback URL generation.
- **Dify-like Token Generation:** Custom JWT-based access and refresh tokens.
- **API Versioning and Pagination:** Built-in support for API versioning (e.g., `/v1/`) and pagination.
- **Structured Logging:** Syslog-ready JSON logging using Loguru for production-grade logging.
- **CLI Operations:** A command-line interface (via Typer) to run the application in development or production and manage migrations.

---

## Purpose and Issues Addressed

### What Problems Are Solved?

- **Centralized Authentication:** Consolidates user authentication via Casdoor, reducing complexity across applications.
- **Seamless SSO Integration:** Provides a uniform SSO flow (login, signup, callback) ensuring consistency across deployments.
- **Token Management:** Implements token generation (access and refresh tokens) in a Dify-like style, making it easier to integrate with existing Dify services.
- **Dynamic URL Handling:** Dynamically creates callback URLs based on the incoming request, reducing hardcoded endpoints and easing deployment across environments.
- **Maintainability and Scalability:** Splits functionality into modular components (e.g., core health checks, auth services) for easier maintenance and potential future extensions.

---

## Architecture and Project Structure

```
dify_auth/
├── apps/
│   ├── auth/                         # Authentication module (SSO with Casdoor integration)
│   │   ├── __init__.py
│   │   ├── routers.py                # Contains endpoints: /login, /signup, /callback
│   │   └── services.py               # Business logic: token generation, OAuth interactions, database handling
│   ├── core/                         # Core utilities and endpoints
│   │   ├── routers/
│   │   │   └── health.py             # Health and version endpoints
│   │   └── cli.py                   # CLI commands to run server/migrations
│   └── main.py                      # Aggregates routers, applies middleware, and configures API versioning
├── conf/
│   ├── logging.py                    # Logging configuration (syslog JSON sink using Loguru)
│   └── settings.py                   # Application settings (environment variables and .env file parsing)
└── manage.py                        # CLI entry point (Typer-based command runner)
```

### Description of Key Components

- **apps/auth/routers.py:**  
  Contains the endpoints for login (`/login`), signup (`/signup`), and callback (`/callback`). Uses FastAPI’s dynamic URL generation (`request.url_for`) to construct callback URLs.

- **apps/auth/services.py:**  
  Implements all business logic such as:
  - Building Casdoor OAuth URLs.
  - Exchanging code for token via OAuth.
  - Parsing JWT tokens using a provided certificate.
  - Handling database interactions to upsert accounts, link integrates, and ensure tenant creation.
  - Generating access and refresh tokens using JWT and Redis.

- **apps/core/routers/health.py:**  
  Provides a basic health-check endpoint to monitor the status and version of the gateway.

- **apps/main.py:**  
  The central application file where routers from the authentication and core modules are aggregated. API versioning is applied here, so endpoints are organized under routes like `/v1/`.

- **conf/settings.py:**  
  Manages environment configurations using Pydantic and dotenv. This makes sure the application parameters (database URLs, secret keys, etc.) are set up correctly.

- **conf/logging.py:**  
  Customizes log output in a JSON syslog format using Loguru, aiding in production logging and monitoring.

- **manage.py & apps/core/cli.py:**  
  Provide a command-line interface to run the server in development (`runserver`) or production (`runprod`) mode and to handle migrations if needed.

---

## Features

- **OAuth with Casdoor:** Easily integrate SSO using Casdoor’s OAuth endpoints.
- **JWT Token Generation:** Creates secure access and refresh tokens mimicking the Dify implementation.
- **Dynamic Callback URLs:** Automatically builds callback URLs dynamically from the request context.
- **Versioned APIs:** Uses `fastapi_versioning` to neatly structure endpoints by version.
- **Pagination Support:** Integrated pagination support using `fastapi_pagination`.
- **Structured JSON Logging:** Logs output in a JSON format suitable for Syslog/centralized logging infrastructures.
- **CLI Management:** Provides commands to run the development server, production server, and perform migrations.

---

## Installation and Setup

### Prerequisites

- Python 3.7 or higher
- A PostgreSQL database (for account and tenant management)
- Redis (for storing refresh tokens)
- [Uvicorn](https://www.uvicorn.org/) installed (check PATH)
- Environment variables setup via a `.env` file (see below)

### Dependencies

Create a `requirements.txt` file with the following (or similar) packages:

```
fastapi
uvicorn
loguru
sqlalchemy
redis
python-dotenv
requests
cryptography
pyjwt
fastapi_pagination
fastapi_versioning
typer
```

Install dependencies using:

```bash
pip install -r requirements.txt
```

---

## Environment Configuration

Create a `.env` file at the root of your project with the following sample contents:

```dotenv
# Server Configuration
BASE_URL=http://127.0.0.1:8000
DEBUG=true

# Database Configuration
DATABASE_URL=postgresql://username:password@hostname:5432/databasename
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432
DB_NAME=yourdb

# Casdoor Credentials
CASDOOR_ENDPOINT=https://casdoor.example.com
CASDOOR_CLIENT_ID=your_client_id
CASDOOR_CLIENT_SECRET=your_client_secret
CASDOOR_ORG_NAME=your_org
CASDOOR_APP_NAME=your_app

# Security
SECRET_KEY=your_secret_key

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password
REDIS_DB=0
```

Adjust the values according to your environment and deployment details.

---

## Usage

### Running in Development Mode

For development with auto-reload enabled, run:

```bash
python manage.py runserver
```

This command invokes Uvicorn, serving the FastAPI application with hot reload enabled.

### Running in Production Mode

For production, run with multiple workers:

```bash
python manage.py runprod --host 0.0.0.0 --port 8000 --workers 4
```

This starts the application in production mode with the specified host, port, and number of workers.

### CLI Commands

The following commands are available via the CLI entry point (`manage.py`):

- **Development Server:**  
  `python manage.py runserver`

- **Production Server:**  
  `python manage.py runprod --host 0.0.0.0 --port 8000 --workers 4`

- **Migrations (if using Alembic):**  
  - Create Migration:  
    `python manage.py makemigrations "Your migration message"`  
  - Apply Migrations:  
    `python manage.py migrate`

---

## How It Works

1. **User Initiates OAuth Flow:**  
   A user visits `/auth/login` or `/auth/signup`. Using FastAPI’s `request.url_for("callback")`, the application dynamically constructs the callback URL to be used by Casdoor.

2. **Redirection to Casdoor:**  
   The corresponding service function builds the Casdoor OAuth URL. The user is then redirected to Casdoor for authentication.

3. **Callback Handling:**  
   After successful authentication, Casdoor redirects back to `/auth/callback` with an authorization code.  
   - The callback endpoint extracts this code and exchanges it for an access token.
   - The returned token is parsed using a public key extracted from a certificate.
   - The application then checks (or creates) the user’s account and associates any necessary integrations in the database.
   - Finally, it generates a Dify-style access token and refresh token. These tokens are sent back (and set as cookies) via a redirect response.

4. **Token Management:**  
   The access token (JWT) and refresh token (stored in Redis) allow the authenticated user to interact with protected endpoints.

5. **API Versioning and Pagination:**  
   The gateway uses API versioning so endpoints are available under paths like `/v1/...`, and integrates pagination support for any endpoints that might need it.

---

## Logging and Error Handling

- **Structured Logging:**  
  Using Loguru, the application outputs logs in a JSON format suitable for syslog integration. The configuration is centralized in `conf/logging.py`.
  
- **Error Handling:**  
  Custom exception handling is implemented for token validation, database schema validation, and OAuth errors. HTTP exceptions are raised with detailed messages.

---

## API Endpoints

### Authentication Endpoints (`/v1/auth/`)

- **GET /auth/login**  
  Initiates the Casdoor login flow. Dynamically generates the callback URL.

- **GET /auth/signup**  
  Initiates the Casdoor signup flow. Uses dynamic callback URL generation.

- **GET /auth/callback**  
  Handles the OAuth callback from Casdoor, exchanges the code for tokens, processes user login, and redirects with token parameters.

### Core Endpoints (`/v1/`)

- **GET /** (Health Check)  
  Returns a welcome message, available versions, and system status.

- **GET /version**  
  Returns API version information.

---

## Additional Considerations

- **Dynamic Callback URL:**  
  By using `request.url_for("callback")` in the login/signup endpoints, the application automatically adapts the callback URL based on the request context. This is especially helpful when deploying across multiple environments (development, staging, production).

- **Database and Migrations:**  
  The package uses SQLAlchemy for database interactions with an automap configuration. Migration commands can be integrated using Alembic if further schema evolution is required.

- **Security:**  
  Ensure that environment variables (especially credentials and secret keys) are properly secured and not exposed in production.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
