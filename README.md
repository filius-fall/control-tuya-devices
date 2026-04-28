# Control Tuya Devices

## Overview
This project interacts with the Tuya cloud to control and manage smart devices. It uses the Tuya API, and you'll need API credentials from the Tuya Developer Platform to get started.

## Installation

### Step 1: Install Poetry
[Poetry](https://python-poetry.org/) is a dependency management and packaging tool for Python.

To install Poetry, run:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Once installed, you can verify the installation with:

```bash
poetry --version
```

### Step 2: Install Project Dependencies

1. Clone this repository:

    ```bash
    git clone git@github.com:filius-fall/control-tuya-devices.git
    cd control-tuya-devices
    ```

2. Use Poetry to install dependencies:

    ```bash
    poetry install
    ```

This will create a virtual environment and install all required packages listed in `pyproject.toml`.

### Step 3: Setting Up Tuya API Credentials

1. Go to the [Tuya Developer Platform](https://developer.tuya.com/).
2. Log in or create an account if you don't have one.
3. Navigate to **Cloud** in the sidebar.
4. If you already have a project, select it. If not, create a new project:
    - Click **Create Project**.
    - Choose the appropriate **Development Method** and **Data Center Region** (such as `in`, `eu`, etc.).
5. In your project, you will see the **Client ID** and **Client Secret** on the dashboard.

### Step 4: Configure Environment Variables

Create a `.env` file in the root of your project directory, and add the following credentials:

```bash
CLIENTKEY="<API Client ID from Tuya dashboard>"
CLIENTSECRET="<API Client Secret from Tuya dashboard>"
APIREGION="<region selected during project creation, e.g., 'in', 'eu'>"
```

### Step 5: Running the Project

Once the environment variables are configured, you can run the project by using:

```bash
poetry run python run.py
```

---
