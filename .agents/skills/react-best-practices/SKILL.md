---
name: react-best-practices
description: Apply React best practices for performance, state management, and component architecture
---

# React Best Practices

1. **State Management**:
   - Keep state local to components where possible; lift state up only when shared across sibling trees.
   - Avoid redundant derived state; compute derived values during render.

2. **Performance Optimization**:
   - Use React.memo, useMemo, and useCallback purposefully to prevent unnecessary re-renders.
   - Implement code-splitting and dynamic imports for non-critical paths.

3. **Code Organization & Cleanliness**:
   - Keep components modular and focused on single responsibilities.
   - Extract custom hooks for complex business logic or data fetching.
