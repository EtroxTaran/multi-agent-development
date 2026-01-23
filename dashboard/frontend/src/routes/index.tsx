/**
 * TanStack Router route tree
 */

import { createRootRoute, createRoute, Outlet } from "@tanstack/react-router";
import { Layout } from "@/components/Layout";
import { ProjectsPage } from "./ProjectsPage";
import { ProjectDashboard } from "./ProjectDashboard";
import { SettingsPage } from "./SettingsPage";

// Root route with layout
const rootRoute = createRootRoute({
  component: () => (
    <Layout>
      <Outlet />
    </Layout>
  ),
});

// Index route (project list)
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: ProjectsPage,
});

// Project dashboard route
const projectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$name",
  component: ProjectDashboard,
});

// Settings route
const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: SettingsPage,
});

// Create the route tree
export const routeTree = rootRoute.addChildren([
  indexRoute,
  projectRoute,
  settingsRoute,
]);
