# Testing Guide

This document describes the comprehensive testing suite for the Conductor multi-agent orchestration system.

## Overview

| Layer | Framework | Target Coverage | Tests |
|-------|-----------|-----------------|-------|
| NestJS Backend | Jest | 80% | ~175 |
| Python Orchestrator-API | pytest | 80% | ~67 |
| Frontend E2E | Playwright | 10 journeys | ~50 |

## Quick Start

### Run All Tests

```bash
# NestJS unit tests with coverage
cd dashboard/backend-nestjs && npm run test:cov

# Python API tests with coverage
pytest tests/orchestrator_api/ --cov=. --cov-report=term-missing

# Playwright E2E tests
cd dashboard/frontend && npm run test:e2e
```

## NestJS Backend Tests

### Location
```
dashboard/backend-nestjs/src/
├── testing/
│   ├── mocks/orchestrator-client.mock.ts
│   └── factories/index.ts
├── orchestrator-client/*.spec.ts
├── websocket/*.spec.ts
├── projects/*.spec.ts
├── workflow/*.spec.ts
├── tasks/*.spec.ts
├── agents/*.spec.ts
├── budget/*.spec.ts
├── chat/*.spec.ts
└── app.controller.spec.ts
```

### Running Tests

```bash
cd dashboard/backend-nestjs

# Run all tests
npm test

# Run with coverage
npm run test:cov

# Run in watch mode
npm run test:watch

# Run specific test file
npm test -- orchestrator-client.service.spec.ts
```

### Test Factories

Use the test factories for consistent mock data:

```typescript
import { createMockOrchestratorClient, MockResponses } from '@/testing/mocks';
import { createProjectSummary, createWorkflowStatus } from '@/testing/factories';

// Create mock client
const mockClient = createMockOrchestratorClient();

// Use predefined responses
mockClient.getProjects.mockResolvedValue(MockResponses.projectsList);

// Or create custom data
const project = createProjectSummary({ name: 'my-project', current_phase: 3 });
```

### Coverage Thresholds

Coverage is enforced at 80% for:
- Branches
- Functions
- Lines
- Statements

## Python Orchestrator-API Tests

### Location
```
tests/orchestrator_api/
├── conftest.py          # Shared fixtures
├── test_health.py       # Health endpoint tests
├── test_projects.py     # Project CRUD tests
├── test_workflow.py     # Workflow operation tests
├── test_tasks.py        # Task endpoint tests
├── test_budget.py       # Budget endpoint tests
└── test_agents.py       # Agent/audit endpoint tests
```

### Running Tests

```bash
# Run all orchestrator-api tests
pytest tests/orchestrator_api/ -v

# Run with coverage
pytest tests/orchestrator_api/ --cov=orchestrator_api --cov-report=html

# Run specific test file
pytest tests/orchestrator_api/test_workflow.py -v

# Run specific test class
pytest tests/orchestrator_api/test_workflow.py::TestStartWorkflow -v
```

### Fixtures

Common fixtures available in `conftest.py`:

```python
# test_client - FastAPI TestClient
def test_example(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200

# temp_project_dir - Temporary project directory
def test_with_project(test_client, temp_project_dir):
    # temp_project_dir has Docs/, .workflow/, etc.
    pass

# mock_project_manager - Mocked ProjectManager
def test_mocked(test_client, mock_project_manager):
    mock_project_manager.list_projects.return_value = [...]
    pass

# mock_orchestrator - Mocked Orchestrator
# mock_budget_manager - Mocked BudgetManager
# mock_audit_storage - Mocked audit storage
```

## Playwright E2E Tests

### Location
```
dashboard/frontend/e2e/
├── page-objects/
│   ├── base.page.ts
│   ├── projects.page.ts
│   └── project-dashboard.page.ts
├── fixtures/
│   ├── mock-data.ts
│   └── api-handlers.ts
└── tests/
    ├── project-navigation.spec.ts
    ├── error-handling.spec.ts
    ├── project-lifecycle.spec.ts
    ├── workflow-control.spec.ts
    ├── websocket-updates.spec.ts
    ├── task-management.spec.ts
    ├── budget-monitoring.spec.ts
    ├── agent-monitoring.spec.ts
    ├── chat-interaction.spec.ts
    └── settings.spec.ts
```

### Running Tests

```bash
cd dashboard/frontend

# Run all E2E tests
npm run test:e2e

# Run with UI mode
npm run test:e2e:ui

# Run specific browser
npx playwright test --project=chromium

# Run specific test file
npx playwright test project-navigation.spec.ts

# Run with headed browser (visible)
npx playwright test --headed

# Debug mode
npx playwright test --debug
```

### User Journeys Tested

| Priority | Journey | Tests |
|----------|---------|-------|
| P0 | Project Navigation | 5 |
| P0 | Error Handling | 6 |
| P1 | Project Lifecycle | 8 |
| P1 | Workflow Control | 6 |
| P1 | WebSocket Updates | 5 |
| P2 | Task Management | 5 |
| P2 | Budget Monitoring | 4 |
| P2 | Agent Monitoring | 4 |
| P3 | Chat Interaction | 4 |
| P3 | Settings | 3 |

### Page Objects

Use page objects for maintainable tests:

```typescript
import { ProjectsPage, ProjectDashboardPage } from './page-objects';
import { setupApiMocks, mockProjects } from './fixtures';

test('example', async ({ page }) => {
  // Setup API mocks
  await setupApiMocks(page, {
    projects: mockProjects.multiple,
  });

  // Use page objects
  const projectsPage = new ProjectsPage(page);
  await projectsPage.goto();
  await projectsPage.openProject('my-project');

  const dashboardPage = new ProjectDashboardPage(page);
  await dashboardPage.switchToTab('tasks');
});
```

### Mock Data

Predefined mock data available:

```typescript
import {
  mockProjects,        // empty, single, multiple
  mockWorkflowStatus,  // notStarted, inProgress, paused, completed, failed
  mockWorkflowHealth,  // healthy, degraded, unhealthy
  mockTasks,           // empty, inProgress, withFailure
  mockBudget,          // normal, nearLimit, disabled
  mockAgents,          // Array of agent status
} from './fixtures';
```

## CI/CD Integration

### GitHub Actions

```yaml
jobs:
  test-nestjs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: cd dashboard/backend-nestjs && npm ci
      - run: cd dashboard/backend-nestjs && npm run test:cov

  test-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e ".[dev]"
      - run: pytest tests/orchestrator_api/ --cov

  test-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: cd dashboard/frontend && npm ci
      - run: npx playwright install --with-deps
      - run: cd dashboard/frontend && npm run test:e2e
```

## Writing New Tests

### NestJS Service Test Template

```typescript
import { Test, TestingModule } from '@nestjs/testing';
import { MyService } from './my.service';
import { createMockOrchestratorClient } from '@/testing/mocks';

describe('MyService', () => {
  let service: MyService;
  let mockClient: ReturnType<typeof createMockOrchestratorClient>;

  beforeEach(async () => {
    mockClient = createMockOrchestratorClient();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        MyService,
        { provide: OrchestratorClientService, useValue: mockClient },
      ],
    }).compile();

    service = module.get<MyService>(MyService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('myMethod', () => {
    it('should return expected result', async () => {
      mockClient.someMethod.mockResolvedValue({ data: 'test' });
      const result = await service.myMethod();
      expect(result).toEqual({ data: 'test' });
    });
  });
});
```

### Python Test Template

```python
import pytest
from unittest.mock import patch, MagicMock

class TestMyEndpoint:
    def test_success(self, test_client, mock_project_manager):
        mock_project_manager.some_method.return_value = {"success": True}

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/my-endpoint")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_not_found(self, test_client, mock_project_manager):
        mock_project_manager.get_project.return_value = None

        with patch("main.get_project_manager", return_value=mock_project_manager):
            response = test_client.get("/my-endpoint/nonexistent")

        assert response.status_code == 404
```

### Playwright Test Template

```typescript
import { test, expect } from '@playwright/test';
import { setupApiMocks, mockProjects } from './fixtures';

test.describe('My Feature', () => {
  test.beforeEach(async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
    });
  });

  test('should do something', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Expected Text')).toBeVisible();
  });
});
```

## Troubleshooting

### NestJS Tests Failing

1. Check mock setup is correct
2. Verify module providers are properly mocked
3. Run with `--verbose` for detailed output

### Python Tests Failing

1. Ensure fixtures are correctly imported
2. Check patch targets match actual import paths
3. Use `pytest -vvs` for verbose output

### Playwright Tests Failing

1. Check API mocks are set up before navigation
2. Use `--debug` mode to step through
3. Check `playwright-report/` for screenshots and traces
