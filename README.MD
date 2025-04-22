# PodiumPro

A modern presentation control system that allows speakers to navigate slides and manage audience questions seamlessly.

## Project Overview

PodiumPro consists of three main components:

1. **Backend**: Server-side application handling presentation state, audience questions, and client communication
2. **Frontend**: Web interface for presenters and audience
3. **Raspberry Pi Client**: Physical controller for navigating presentations and recording audience questions

## Component Documentation

- [Backend Documentation](./backend/README.md) - API, server setup, and core functionality
- [Frontend Documentation](./frontend/README.md) - UI, features, and user guide

## Raspberry Pi Integration

For physical control of presentations, PodiumPro supports a Raspberry Pi client with joystick navigation and audio recording capabilities. This allows presenters to:

- Navigate slides using a physical joystick
- Record audience questions with the press of a button
- Maintain wireless connection to the presentation

See the [PodiumPro Raspberry Pi Client](https://github.com/bjarkividars/PodiumPro-pi-client) repository for hardware requirements, setup instructions, and usage details.

## Quick Start

1. Set up the backend server (see backend README)
2. Configure and deploy the frontend (see frontend README)
3. Optional: Set up the Raspberry Pi client for physical control
