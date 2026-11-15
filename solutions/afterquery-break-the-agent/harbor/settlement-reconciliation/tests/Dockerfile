FROM python:3.12.8-slim

# Separate verifier: the agent container and all agent-authored executables are
# destroyed before this image starts. Only configured artifacts are forwarded.
WORKDIR /tests
COPY . /tests/
RUN mkdir -p /app/data /app/output /logs/verifier
CMD ["sleep", "infinity"]
