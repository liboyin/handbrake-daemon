FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04

ARG APT_PROXY
ARG PYPI_PROXY

ENV DEBIAN_FRONTEND=noninteractive \
    NVIDIA_DRIVER_CAPABILITIES=all \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1

COPY --chown=ubuntu . /workspaces/handbrake-daemon
WORKDIR /workspaces/handbrake-daemon

RUN ./docker_apt_install.sh
RUN ./docker_pip_install.sh

USER ubuntu
ENTRYPOINT ["python", "handbrake_daemon"]
