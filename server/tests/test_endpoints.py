import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Onchain Explorer Server"
    assert "endpoints" in data


def test_healthz_endpoint():
    """Test health check endpoint"""
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_query_endpoint():
    """Test query endpoint"""
    query_data = {"query": "test query"}
    response = client.post("/api/v1/query", json=query_data)
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "metadata" in data
