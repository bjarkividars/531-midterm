# PodiumPro

This project consists of a backend server that directly controls your presentation software and web browser based on input from a Raspberry Pi client.

## System Overview

PodiumPro is designed to give presenters complete control of their presentations using a physical Raspberry Pi controller with a joystick and button. Unlike traditional presentation systems with separate frontend applications, PodiumPro works by having the backend directly control your existing applications:

- **Direct Application Control**: The backend uses system automation to control Figma, PowerPoint, or other presentation software
- **Browser Control**: Scrolling through AI responses in your browser is handled by direct keyboard input from the backend
- **Knowledge Base Management**: Uploaded files are processed for question answering

## Technical Implementation

The backend server handles:
- Receiving joystick input from the Raspberry Pi
- Directly controlling your presentation software with left/right arrow key presses
- Controlling your browser's scrolling with up/down key presses
- Processing audio questions via speech-to-text
- Generating AI-powered answers using the knowledge base
- Serving a simple web interface for knowledge base management

## Knowledge Base Management

The system provides a simple web interface for:
- Uploading new documents to the knowledge base
- Viewing existing knowledge base files
- Deleting documents from the knowledge base

This interface is accessible through your web browser, but the main presentation control happens through direct system automation.

## Physical Control System

The PodiumPro system is controlled through a Raspberry Pi with:
- A joystick for navigation and scrolling
  - Left/Right: Navigate slides in your presentation software
  - Up/Down: Scroll through responses in your browser
- A button for recording audience questions

## Setup Requirements

1. **Backend Server**
   - Running locally on the presenter's computer
   - Has permission to control applications (accessibility permissions on macOS)
   - Connected to the Raspberry Pi client

2. **Presentation Environment**
   - Figma, PowerPoint, or other compatible presentation software
   - Web browser for viewing AI-generated responses
   - Both applications should be open during presentations

3. **Raspberry Pi Client**
   - Connected to the same network as the presenter's computer
   - Properly configured with joystick and microphone

## Usage

1. Start the backend server on your computer
2. Open your presentation software (Figma, PowerPoint, etc.)
3. Open a web browser for viewing responses
4. Connect the Raspberry Pi client to the backend
5. Control your presentation:
   - Navigate slides with left/right joystick movements
   - Scroll through responses with up/down joystick movements
   - Record audience questions by pressing the button

## Integration with Raspberry Pi

The physical control is handled through the [PodiumPro Raspberry Pi Client](https://github.com/bjarkividars/PodiumPro-pi-client). The Pi client provides:
- Physical joystick navigation for direct slide control
- Button-activated recording of audience questions
- Direct audio transmission to the backend

## Troubleshooting

- If application control isn't working, check system permissions (Accessibility settings on macOS)
- For connectivity issues, verify the Raspberry Pi client is properly connected to the backend
- If questions aren't being processed, check the backend logs for API or service errors