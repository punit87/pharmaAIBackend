#!/bin/bash

# Script to delete all Docker containers and images

echo "Starting Docker cleanup..."

# Step 1: Stop all running containers
echo "Stopping all running containers..."
if [ -n "$(docker ps -q)" ]; then
  docker stop $(docker ps -q)
else
  echo "No running containers to stop."
fi

# Step 2: Delete all containers (running and stopped)
echo "Deleting all containers..."
if [ -n "$(docker ps -a -q)" ]; then
  docker rm -f $(docker ps -a -q)
else
  echo "No containers to delete."
fi

# Step 3: Delete all images
echo "Deleting all images..."
if [ -n "$(docker images -q)" ]; then
  docker rmi -f $(docker images -q | sort -u)
else
  echo "No images to delete."
fi

# Step 4: Clean up unused Docker objects (volumes, networks, etc.)
echo "Cleaning up unused Docker objects..."
docker system prune -a -f --volumes

# Step 5: Verify cleanup
echo "Verifying cleanup..."
CONTAINERS=$(docker ps -a -q)
IMAGES=$(docker images -q)

if [ -z "$CONTAINERS" ] && [ -z "$IMAGES" ]; then
  echo "Cleanup successful! No containers or images remain."
else
  echo "Warning: Cleanup incomplete."
  [ -n "$CONTAINERS" ] && echo "Remaining containers: $(docker ps -a)"
  [ -n "$IMAGES" ] && echo "Remaining images: $(docker images)"
fi

echo "Docker cleanup completed."