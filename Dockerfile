# Basic docker image for PGScout
# It runs by adding "pgscout-url: http://PGScout:4242/iv" to your RM config
# Usage:
#   docker build -t PGScout
#   docker run -d --net container:RocketMap --name PGSCout -P PGScout
# Change "RocketMap" to the name of your RocketMap docker
# For newer versions of docker maybe you have to change --net to --network

FROM python:2.7-alpine

# Default port the webserver runs on
EXPOSE 4242

# Working directory for the application
WORKDIR /usr/src/app

# Set Entrypoint with hard-coded options
ENTRYPOINT ["python", "./pgscout.py", "--host", "0.0.0.0"]

# Install required system packages
RUN apk add --no-cache ca-certificates
RUN apk add --no-cache bash git openssh
RUN apk add --no-cache linux-headers

COPY requirements.txt /usr/src/app/

RUN apk add --no-cache build-base \
 && pip install --no-cache-dir -r requirements.txt \
 && apk del build-base

# Copy everything to the working directory (Python files, templates, config) in one go.
COPY . /usr/src/app/
