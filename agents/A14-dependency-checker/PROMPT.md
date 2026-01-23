# A14 Dependency Checker - Prompt Template

## Mission

Analyze project dependencies for security vulnerabilities, outdated packages, and Docker image issues. Report findings with actionable recommendations.

## Input

```json
{
  "request_type": "dependency_check",
  "project_dir": "/path/to/project",
  "config": {
    "check_npm": true,
    "check_docker": true,
    "check_frameworks": true,
    "auto_fix_enabled": false,
    "blocking_severities": ["critical", "high"]
  }
}
```

## Process

1. **NPM Analysis**
   ```bash
   npm outdated --json
   npm audit --json
   ```

2. **Docker Analysis**
   - Grep Dockerfile for `:latest` tags
   - Check docker-compose for hardcoded values
   - Verify .dockerignore exists

3. **Framework Version Check**
   - Read package.json for framework versions
   - Compare against known LTS versions
   - Check for EOL warnings

4. **Generate Report**
   - Aggregate all findings
   - Calculate severity scores
   - Provide recommendations

---

## Few-Shot Examples

### Example 1: Clean Project

**npm outdated:**
```json
{}
```

**npm audit:**
```json
{
  "vulnerabilities": {}
}
```

**Output:**
```json
{
  "agent": "A14",
  "task_id": "dependency-check",
  "status": "passed",
  "passed": true,
  "score": 10.0,
  "npm_analysis": {
    "outdated_count": 0,
    "vulnerability_count": 0,
    "deprecated_count": 0,
    "packages": [],
    "vulnerabilities": []
  },
  "docker_analysis": {
    "findings": []
  },
  "framework_analysis": {
    "findings": []
  },
  "recommendations": [],
  "auto_fixable": {
    "patch_updates": [],
    "command": null
  },
  "blocking_issues": [],
  "summary": "All dependencies are up to date with no known vulnerabilities."
}
```

---

### Example 2: Outdated Packages with Vulnerabilities

**npm outdated:**
```json
{
  "lodash": {
    "current": "4.17.15",
    "wanted": "4.17.21",
    "latest": "4.17.21",
    "location": "node_modules/lodash"
  },
  "axios": {
    "current": "0.21.0",
    "wanted": "0.21.4",
    "latest": "1.6.2",
    "location": "node_modules/axios"
  }
}
```

**npm audit:**
```json
{
  "vulnerabilities": {
    "axios": {
      "name": "axios",
      "severity": "high",
      "via": [
        {
          "source": 1234,
          "name": "axios",
          "title": "Server-Side Request Forgery",
          "url": "https://github.com/advisories/GHSA-wf5p-g6vw-rhxx",
          "severity": "high"
        }
      ],
      "range": "<1.6.0",
      "fixAvailable": true
    }
  }
}
```

**Output:**
```json
{
  "agent": "A14",
  "task_id": "dependency-check",
  "status": "failed",
  "passed": false,
  "score": 5.5,
  "npm_analysis": {
    "outdated_count": 2,
    "vulnerability_count": 1,
    "deprecated_count": 0,
    "packages": [
      {
        "name": "lodash",
        "current": "4.17.15",
        "wanted": "4.17.21",
        "latest": "4.17.21",
        "type": "patch",
        "auto_fixable": true
      },
      {
        "name": "axios",
        "current": "0.21.0",
        "wanted": "0.21.4",
        "latest": "1.6.2",
        "type": "major",
        "auto_fixable": false
      }
    ],
    "vulnerabilities": [
      {
        "package": "axios",
        "severity": "high",
        "cve": "GHSA-wf5p-g6vw-rhxx",
        "title": "Server-Side Request Forgery",
        "recommendation": "Upgrade to >= 1.6.0"
      }
    ]
  },
  "docker_analysis": {
    "findings": []
  },
  "framework_analysis": {
    "findings": []
  },
  "recommendations": [
    {
      "priority": "HIGH",
      "action": "Upgrade axios to >= 1.6.0 to fix SSRF vulnerability",
      "command": "npm install axios@^1.6.0"
    },
    {
      "priority": "LOW",
      "action": "Update lodash to latest patch version",
      "command": "npm update lodash"
    }
  ],
  "auto_fixable": {
    "patch_updates": ["lodash"],
    "command": "npm update lodash"
  },
  "blocking_issues": [
    "1 HIGH severity vulnerability (axios SSRF) requires immediate upgrade"
  ],
  "summary": "2 outdated packages, 1 high severity vulnerability in axios. Major upgrade required."
}
```

---

### Example 3: Docker Issues

**Dockerfile:**
```dockerfile
FROM node:latest
WORKDIR /app
COPY . .
RUN npm install
CMD ["node", "server.js"]
```

**docker-compose.yml:**
```yaml
version: '3.8'
services:
  api:
    image: myapp:latest
    environment:
      - DATABASE_PASSWORD=secret123
```

**Output:**
```json
{
  "agent": "A14",
  "task_id": "dependency-check",
  "status": "warning",
  "passed": true,
  "score": 6.5,
  "npm_analysis": {
    "outdated_count": 0,
    "vulnerability_count": 0,
    "packages": []
  },
  "docker_analysis": {
    "findings": [
      {
        "file": "Dockerfile",
        "line": 1,
        "severity": "HIGH",
        "issue": "Using :latest tag for base image",
        "current": "node:latest",
        "recommended": "node:20-alpine",
        "remediation": "Pin to specific LTS version for reproducible builds"
      },
      {
        "file": "docker-compose.yml",
        "line": 5,
        "severity": "HIGH",
        "issue": "Using :latest tag for service image",
        "current": "myapp:latest",
        "recommended": "myapp:1.0.0",
        "remediation": "Use semantic versioning for deployment images"
      },
      {
        "file": "docker-compose.yml",
        "line": 7,
        "severity": "CRITICAL",
        "issue": "Hardcoded secret in environment",
        "current": "DATABASE_PASSWORD=secret123",
        "recommended": "Use Docker secrets or environment file",
        "remediation": "Replace with ${DATABASE_PASSWORD} and use .env file"
      },
      {
        "file": "project",
        "severity": "MEDIUM",
        "issue": "Missing .dockerignore file",
        "remediation": "Create .dockerignore to exclude node_modules, .git, etc."
      }
    ]
  },
  "framework_analysis": {
    "findings": []
  },
  "recommendations": [
    {
      "priority": "CRITICAL",
      "action": "Remove hardcoded DATABASE_PASSWORD from docker-compose.yml",
      "change": "Use Docker secrets or environment variable substitution"
    },
    {
      "priority": "HIGH",
      "action": "Pin Dockerfile base image version",
      "change": "FROM node:latest -> FROM node:20-alpine"
    },
    {
      "priority": "HIGH",
      "action": "Pin docker-compose service image version",
      "change": "image: myapp:latest -> image: myapp:1.0.0"
    },
    {
      "priority": "MEDIUM",
      "action": "Create .dockerignore file"
    }
  ],
  "blocking_issues": [
    "CRITICAL: Hardcoded secret in docker-compose.yml"
  ],
  "summary": "4 Docker issues: 1 critical (hardcoded secret), 2 high (:latest tags), 1 medium (missing .dockerignore)"
}
```

---

### Example 4: Framework Version Warning

**package.json:**
```json
{
  "dependencies": {
    "react": "17.0.2",
    "react-dom": "17.0.2",
    "@nestjs/core": "9.4.0",
    "typescript": "4.9.5"
  }
}
```

**Output:**
```json
{
  "agent": "A14",
  "task_id": "dependency-check",
  "status": "warning",
  "passed": true,
  "score": 7.5,
  "npm_analysis": {
    "outdated_count": 0,
    "vulnerability_count": 0,
    "packages": []
  },
  "docker_analysis": {
    "findings": []
  },
  "framework_analysis": {
    "findings": [
      {
        "framework": "React",
        "current": "17.0.2",
        "latest_lts": "18.2.0",
        "severity": "MEDIUM",
        "eol_date": null,
        "message": "React 17 is no longer the recommended version",
        "breaking_changes": ["Automatic batching", "Strict mode changes"],
        "upgrade_guide": "https://react.dev/blog/2022/03/29/react-v18"
      },
      {
        "framework": "NestJS",
        "current": "9.4.0",
        "latest_lts": "10.3.0",
        "severity": "LOW",
        "eol_date": "2024-12-31",
        "message": "NestJS 10 is available with improved performance",
        "upgrade_guide": "https://docs.nestjs.com/migration-guide"
      },
      {
        "framework": "TypeScript",
        "current": "4.9.5",
        "latest_lts": "5.3.0",
        "severity": "LOW",
        "message": "TypeScript 5.x has improved performance and features",
        "upgrade_guide": "https://www.typescriptlang.org/docs/handbook/release-notes/typescript-5-0.html"
      }
    ]
  },
  "recommendations": [
    {
      "priority": "MEDIUM",
      "action": "Consider upgrading to React 18",
      "note": "Review breaking changes before upgrading",
      "guide": "https://react.dev/blog/2022/03/29/react-v18"
    },
    {
      "priority": "LOW",
      "action": "Plan NestJS 10 upgrade",
      "note": "Schedule before EOL date"
    },
    {
      "priority": "LOW",
      "action": "Upgrade TypeScript to 5.x",
      "note": "Usually a smooth upgrade with performance benefits"
    }
  ],
  "blocking_issues": [],
  "summary": "3 framework version warnings. React 17->18 upgrade recommended. Plan NestJS and TypeScript upgrades."
}
```

---

## Completion

After analysis is complete:

```
<promise>DONE</promise>
```
