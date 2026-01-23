# Documentation Access

## MCP Ref Tools

You have access to documentation lookup tools via MCP Ref:

- **`mcp__Ref__ref_search_documentation`**: Search for documentation on frameworks, libraries, and APIs
- **`mcp__Ref__ref_read_url`**: Read the content of a documentation URL as markdown

## When to Use

**DO use ref tools when:**
- Working with unfamiliar APIs or libraries
- Debugging issues that may be related to external dependencies
- Need to verify correct usage patterns for a framework
- Looking up best practices for security, performance, or accessibility
- Checking for breaking changes in dependency updates

**DO NOT use ref tools when:**
- The answer is in the local codebase (use Read/Grep/Glob instead)
- Making simple changes that don't involve external dependencies
- The information is already provided in the task context
- Working with internal/proprietary APIs (use local documentation)

## Best Practices

1. **Search first**: Use `ref_search_documentation` to find relevant docs before reading
2. **Be specific**: Include programming language and framework names in searches
3. **Prefer official docs**: Official documentation is more reliable than blog posts
4. **Verify versions**: Ensure documentation matches the version in use
5. **Cache results mentally**: Don't repeatedly search for the same information

## Example Usage

```
# Search for React hook documentation
ref_search_documentation("React useEffect cleanup function best practices")

# Read a specific documentation URL
ref_read_url("https://react.dev/reference/react/useEffect#specifying-reactive-dependencies")
```

## Fallback

If ref tools are unavailable or fail, you can use WebSearch and WebFetch as alternatives:

- **WebSearch**: General web search for documentation
- **WebFetch**: Fetch and read content from a specific URL
