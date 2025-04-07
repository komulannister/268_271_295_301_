import json
import uuid
import subprocess
from flask import Flask, jsonify, request
from datetime import datetime, timedelta
import threading
import time

app = Flask(__name__)

NODES_FILE = "nodes.json"
PODS_FILE = "pods.json"

# Load existing nodes from file
def load_nodes():
    try:
        with open(NODES_FILE, "r") as f:
            data = f.read()
            return json.loads(data) if data else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Load existing pods from file
def load_pods():
    try:
        with open(PODS_FILE, "r") as f:
            data = f.read()
            return json.loads(data) if data else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Save nodes to file
def save_nodes():
    with open(NODES_FILE, "w") as f:
        json.dump(nodes, f, indent=4)

# Save pods to file
def save_pods():
    with open(PODS_FILE, "w") as f:
        json.dump(pods, f, indent=4)

nodes = load_nodes()
pods = load_pods()

@app.route('/list_nodes', methods=['GET'])
def list_nodes():
    return jsonify(nodes)

@app.route('/add_node', methods=['POST'])
def add_node():
    data = request.get_json()
    node_id = str(uuid.uuid4())
    nodes[node_id] = {
        **data,
        "last_heartbeat": datetime.utcnow().isoformat(),
        "status": "active"
    }
    save_nodes()

    # Start Docker container
    container_name = f"node_{node_id}"
    image_name = "alpine"  # Replace with your image if needed
    command = ["docker", "run", "-d", "--name", container_name, image_name, "sleep", "infinity"]
    try:
        container_id = subprocess.check_output(command).decode().strip()
        nodes[node_id]["container_id"] = container_id
        save_nodes()
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Failed to start Docker container", "details": str(e)}), 500

    return jsonify({"message": f"Node {node_id} added and container started", "node_id": node_id})

@app.route('/remove_node', methods=['DELETE'])
def remove_node():
    data = request.get_json()
    node_id = data.get("node_id")

    if node_id in nodes:
        container_id = nodes[node_id].get("container_id")
        if container_id:
            try:
                subprocess.run(["docker", "rm", "-f", container_id], check=True)
            except subprocess.CalledProcessError:
                pass  # Ignore if the container was already removed
        del nodes[node_id]
        save_nodes()
        return jsonify({"message": f"Node {node_id} removed"})
    else:
        return jsonify({"error": "Node not found"}), 404

@app.route('/schedule_pod', methods=['POST'])
def schedule_pod():
    data = request.get_json()
    required_cpu = data.get("cpu", 0)
    required_disk = data.get("disk", 0)
    required_ram = data.get("ram", 0)

    for node_id, resources in nodes.items():
        if nodes[node_id].get("status") == "active" and \
           resources.get("cpu", 0) >= required_cpu and \
           resources.get("disk", 0) >= required_disk and \
           resources.get("ram", 0) >= required_ram:

            pod_id = str(uuid.uuid4())
            pods[pod_id] = {
                "node_id": node_id,
                "cpu": required_cpu,
                "disk": required_disk,
                "ram": required_ram
            }
            save_pods()

            return jsonify({"message": f"Pod {pod_id} scheduled on {node_id}", "pod_id": pod_id, "node_id": node_id})

    return jsonify({"error": "No suitable node found"}), 400

@app.route('/list_pods', methods=['GET'])
def list_pods():
    return jsonify(pods)

@app.route('/delete_pod', methods=['DELETE'])
def delete_pod():
    data = request.get_json()
    pod_id = data.get("pod_id")

    if pod_id in pods:
        del pods[pod_id]
        save_pods()
        return jsonify({"message": f"Pod {pod_id} deleted successfully"})
    else:
        return jsonify({"error": "Pod not found"}), 404

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.get_json()
    node_id = data.get("node_id")

    if node_id in nodes:
        nodes[node_id]["last_heartbeat"] = datetime.utcnow().isoformat()
        nodes[node_id]["status"] = "active"
        save_nodes()
        return jsonify({"message": f"Heartbeat received from {node_id}"}), 200
    return jsonify({"error": "Node not found"}), 404

def monitor_node_health(interval=10, timeout=30):
    while True:
        now = datetime.utcnow()
        for node_id in list(nodes.keys()):
            last_beat = nodes[node_id].get("last_heartbeat")
            if last_beat:
                last_beat_time = datetime.fromisoformat(last_beat)
                if now - last_beat_time > timedelta(seconds=timeout):
                    print(f"[Monitor] Node {node_id} is inactive.")
                    nodes[node_id]["status"] = "inactive"
                else:
                    nodes[node_id]["status"] = "active"
            else:
                nodes[node_id]["status"] = "inactive"
        save_nodes()
        time.sleep(interval)

# Start health monitoring thread
health_thread = threading.Thread(target=monitor_node_health, daemon=True)
health_thread.start()

if __name__ == '__main__':
    app.run(debug=True)
