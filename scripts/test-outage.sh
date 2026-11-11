#!/usr/bin/env bash

# ==================================================
# 1. SETTINGS — executed immediately
# ==================================================

# Enable strict mode for better error handling
set -Eeuo pipefail

# Run from the repository root, even when called from another directory.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

#Each test run gets its own unique namespace to avoid conflicts with other test runs.
project_name="redis-test-$(date +%s)-$$"
wait_seconds="${TEST_WAIT_SECONDS:-60}"


if ! [[ "$wait_seconds" =~ ^[1-9][0-9]*$ ]]; then
  echo "Error: TEST_WAIT_SECONDS must be a positive integer."
  exit 1
fi


# ==================================================
# 2. FUNCTIONS — executed when called
# ==================================================

compose() {
  # $@ represents all the arguments passed to the compose function, allowing it to forward any command-line arguments to the docker compose command.
  docker compose -p "$project_name" "$@"
}

# the function is called when the script exits, either normally or due to an error. It ensures that any resources created during the test are cleaned up properly.
cleanup() {
    # result here is the exit code of the last command executed before the trap was triggered
    result=$?
    # trap here to ensure cleanup happens even if the script exits due to an error
    trap - EXIT
    # here -ne is used to check if the result is not equal to 0, indicating a failure
    if [ "$result" -ne 0 ]; then
        echo "FAIL: collecting container status and logs for debugging..."
        # here we use '|| true' to ensure that even if the command fails, the script continues to execute
        compose ps -a || true
        # || true is used to ensure that even if the command fails, the script continues to execute
        compose logs --no-color --tail=200 || true
        fi
    echo "Cleaning up test environment..."
    # here ! is used to negate the exit status of the command, so if the command fails, the script will print a warning message and set the result to 1 to indicate failure in cleanup.
    if ! compose down --volumes --remove-orphans; then
        echo "Warning: Failed to clean up test environment. Please check Docker for any remaining resources."
        result=1  # Set result to 1 to indicate failure in cleanup
    fi

    # Exit with the original result code to indicate success or failure of the test run
    exit $result


}

wait_for_message(){
    # local is used to declare variables that are only accessible within the function, preventing them from affecting the global scope.
    # and here message is used to store the first argument passed to the function, which is expected to be a message indicating what the script is waiting for.
    local message="$1"
    local deadline=$((SECONDS + wait_seconds))
    local logs
    # lt is used to compare the current value of SECONDS with the deadline, and the loop continues until the current time exceeds the deadline.
    while [ "$SECONDS" -lt "$deadline" ]; do
        logs=$(compose logs --no-color --tail=200)
        # -q is used to suppress the output of grep, so it only returns the exit status indicating whether the pattern was found or not.
        if echo "$logs" | grep -q "$message"; then
            return 0
        fi
        sleep 1
    done
}

# ==================================================
# 3. TRAPS — register exit and signal handling
# ==================================================

#here we set up traps to ensure that the cleanup function is called when the script exits, and to handle specific signals like INT (interrupt) and TERM (terminate) gracefully.
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ==================================================
# 4. TEST STEPS — main sequence starts here
# ==================================================

echo "Validating Compose configuration..."
compose config >/dev/null

echo "Starting test environment..."
compose up -d --wait --wait-timeout 120

echo "Waiting for the first successful connection..."
wait_for_message "OK: Redis is reachable"

echo "Stopping Redis to simulate an outage..."
compose stop redis

echo "Waiting for the outage alert..."
wait_for_message "ALERT:"

echo "Restoring Redis service..."
compose start redis

echo "Waiting for the recovery message..."
wait_for_message "RECOVERED:"

echo "PASS: Startup, outage, and recovery test completed successfully."










