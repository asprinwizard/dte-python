import os
import shutil
import subprocess
import sys

def load_config(default_file="config.txt", user_file=".config"):
    # If .config doesn't exist, create it from config.txt
    if not os.path.exists(user_file):
        print(f"{user_file} not found. Creating from {default_file}.")
        shutil.copy(default_file, user_file)

    # Load the config from .config
    config = {}
    try:
        with open(user_file, 'r') as file:
            for line in file:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    config[key.strip()] = value.strip()
    except FileNotFoundError:
        print(f"{user_file} was unexpectedly deleted. Resetting config.")
        reset()  # Call reset if .config is deleted while running

    return config

def reset():
    """Delete .config and restart the script."""
    user_file = ".config"
    if os.path.exists(user_file):
        os.remove(user_file)
        print(f"{user_file} deleted. Restarting...")

    # Restart the script using subprocess
    subprocess.Popen([sys.executable] + sys.argv)
    sys.exit()  # Exit the current instance

# Main script usage
if __name__ == "__main__":
    config = load_config()

    # Example usage of the loaded config
    print("Loaded Config:", config)

    # Example call to reset (if needed in certain conditions)
    # reset()
