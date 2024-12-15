FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu24.04

ARG APT_PROXY=http://192.168.0.4:3142
ARG PYPI_PROXY=http://192.168.0.4:3141/root/pypi/+simple/
ENV DEBIAN_FRONTEND=noninteractive
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=all

COPY . /workspaces/handbrake-daemon
WORKDIR /workspaces/handbrake-daemon
RUN chown -R ubuntu:ubuntu /workspaces/handbrake-daemon

RUN ./docker_apt_install.sh
RUN ./docker_pip_install.sh

USER ubuntu
