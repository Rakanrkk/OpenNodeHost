# OpenNodeHost

OpenNodeHost is a remote execution runtime for AI agents.

It is designed for a setup where one agent remains the single planner/orchestrator, while remote Linux, Windows, and WSL2 machines act as execution nodes.

## Problem

Current approaches usually fall into one of these buckets:

- raw SSH command execution
- terminal scraping via tmux/screen
- MCP wrappers around SSH
- traditional automation frameworks like Ansible

These are useful, but they each leave gaps for agent-centric remote execution:

- command quoting and shell nesting become fragile
- large output is awkward to stream or page
- session state is not always a first-class concept
- execution status is often inferred from text instead of modeled explicitly
- Windows/Linux/WSL2 support is often uneven

## Project Goal

OpenNodeHost aims to provide a small, durable execution layer with these properties:

- agent-agnostic core
- SSH-friendly transport model
- persistent node/session/exec abstractions
- structured stdout/stderr/exit-code handling
- paged output retrieval
- compatibility with Linux, Windows, and WSL2
- adapters for CLI, MCP, and API use

## Non-Goals

OpenNodeHost is not intended to be:

- another full autonomous coding agent
- a replacement for Ansible/Terraform/Salt
- a terminal UI product
- a remote desktop system
- a general-purpose cloud orchestration platform

## Architecture Direction

High-level architecture:

- controller plane: the user-facing orchestrator/agent
- transport plane: initially SSH-backed
- node plane: lightweight remote node host on each machine
- execution plane: local shell / PowerShell subprocess management on the node

Core objects:

- Node
- Session
- Exec

## Initial Scope

The initial version should focus on:

1. remote node host process
2. session lifecycle
3. command execution lifecycle
4. output buffering and pagination
5. Linux support first
6. Windows and WSL2 support next
7. MCP adapter after core runtime is stable

## Why this project exists

This project exists because there does not appear to be a widely adopted open-source runtime that cleanly fills the gap between:

- simple SSH wrappers
- traditional ops automation frameworks
- full remote device/node control planes such as OpenClaw nodes

## Status

Project bootstrapping.
