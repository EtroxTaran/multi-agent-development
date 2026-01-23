import { test, expect } from '@playwright/test';

test.describe('Workflow Visualization', () => {
  const projectName = 'test-project';

  test.beforeEach(async ({ page }) => {
    // Mock project details
    await page.route(`/api/projects/${projectName}`, async (route) => {
      await route.fulfill({
        json: {
          name: projectName,
          path: `/tmp/${projectName}`,
          config: {},
          state: { current_phase: 1 },
          files: {},
          phases: {}
        }
      });
    });

    // Mock workflow status
    await page.route(`/api/projects/${projectName}/workflow/status`, async (route) => {
      await route.fulfill({
        json: {
          mode: 'langgraph',
          status: 'not_started',
          project: projectName,
          current_phase: 1,
          phase_status: {},
          pending_interrupt: null
        }
      });
    });

    // Mock workflow health
    await page.route(`/api/projects/${projectName}/workflow/health`, async (route) => {
      await route.fulfill({
        json: {
          status: 'healthy',
          project: projectName,
          current_phase: 1,
          agents: { claude: true, gemini: true, cursor: true }
        }
      });
    });

    // Mock tasks
    await page.route(`/api/projects/${projectName}/tasks`, async (route) => {
      await route.fulfill({
        json: { tasks: [], total: 0, completed: 0, in_progress: 0, pending: 0, failed: 0 }
      });
    });

    // Mock graph definition
    await page.route(`/api/projects/${projectName}/workflow/graph`, async (route) => {
      await route.fulfill({
        json: {
          nodes: [
            { id: 'planning', data: { label: 'Planning' } },
            { id: 'implementation', data: { label: 'Implementation' } }
          ],
          edges: [
            { source: 'planning', target: 'implementation' }
          ]
        }
      });
    });
  });

  test('should display workflow graph tab', async ({ page }) => {
    await page.goto(`/project/${projectName}`);
    
    // Check if we are on the dashboard
    await expect(page.getByRole('heading', { name: projectName })).toBeVisible();
    
    // Check for tabs
    await expect(page.getByRole('tab', { name: 'Graph' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Tasks' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Chat' })).toBeVisible();

    // Click Graph tab
    await page.getByRole('tab', { name: 'Graph' }).click();
    
    // Check if graph nodes are visible (mocked)
    // Note: React Flow nodes might take a moment to render
    await expect(page.getByText('Planning')).toBeVisible();
    await expect(page.getByText('Implementation')).toBeVisible();
  });

  test('should open start workflow dialog', async ({ page }) => {
    await page.goto(`/project/${projectName}`);
    
    // Click Start Workflow button
    await page.getByRole('button', { name: 'Start Workflow' }).click();
    
    // Check dialog content
    await expect(page.getByRole('heading', { name: 'Start Workflow' })).toBeVisible();
    await expect(page.getByText('Start Phase')).toBeVisible();
    await expect(page.getByText('End Phase')).toBeVisible();
    
    // Check checkboxes
    await expect(page.getByLabel('Skip Validation')).toBeVisible();
    await expect(page.getByLabel('Autonomous')).toBeVisible();
  });

  test('should display HITL chat state', async ({ page }) => {
    // Override status to be paused
    await page.route(`/api/projects/${projectName}/workflow/status`, async (route) => {
      await route.fulfill({
        json: {
          mode: 'langgraph',
          status: 'paused',
          project: projectName,
          current_phase: 2,
          phase_status: {},
          pending_interrupt: { paused_at: ['approval_gate'] }
        }
      });
    });

    await page.goto(`/project/${projectName}`);
    
    // Click Chat tab
    await page.getByRole('tab', { name: 'Chat' }).click();
    
    // Check for paused indicator
    await expect(page.getByText('Input Required')).toBeVisible();
    await expect(page.getByPlaceholder('Enter your response to continue...')).toBeVisible();
  });
});
