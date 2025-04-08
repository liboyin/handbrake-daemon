FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

ARG APT_PROXY
ARG PYPI_PROXY

ENV DEBIAN_FRONTEND=noninteractive
ENV NVIDIA_DRIVER_CAPABILITIES=all
ENV PYTHONFAULTHANDLER=1

COPY --chown=ubuntu . /workspaces/handbrake-daemon
WORKDIR /workspaces/handbrake-daemon

RUN ./docker_apt_install.sh
RUN ./docker_pip_install.sh

USER ubuntu
ENTRYPOINT ["/workspaces/handbrake-daemon/entrypoint.sh"]
