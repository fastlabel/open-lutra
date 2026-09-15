# Coding Style

## General

- **Write comments and docstrings in English** (variable, function, and class names are also in English)
- **Comments should describe "what the code does, its current responsibility, and design constraints"**. Do not describe the implementation history (e.g., "this used to be X", "abstracted because of duplication", "split during refactor"). History belongs in commit messages or PR descriptions; only the information a reader needs should remain in comments.
  - ❌ `// abstracted this because the same pattern existed in two routes`
  - ✅ `// returns the list of recording folders as FileRow[]. The reference is stable via useMemo`

## Python

- Lint + format with **ruff** (line length: 120)
- **mypy** strict mode (type annotations required)
- Method order: `__init__` → public → private (newspaper-article style)
- Public method order should match the order of the corresponding API endpoints
- Import order is auto-sorted by ruff (isort)
- **Do not assign default values to pydantic response model fields** (use `field: int`, not `field: int = 0`). With a default value, the field is dropped from `required` in OpenAPI, and orval generates the TypeScript type as `field?: number` (optional). This forces lots of `?? 0` fallbacks on the frontend and prevents null safety from being guaranteed by the type system, so make fields required on the assumption that the server always provides a value. Express fields that can be null as `field: int | None` (no default). When loading legacy-format JSON from old caches, catch `ValidationError` in the load function and return None to let regeneration take over.

## TypeScript / React

- Lint + format with **biome**
- Type-check with **tsc --noEmit** (strict mode)
- Use **lucide-react** for icons (not inline SVG or emoji)
- **font-size must be 13px or larger** (applies to CSS, inline styles, and Canvas rendering)
- **Use orval-generated API response/request fields in server naming (snake_case) as-is**. Do not convert via `const fooBar = resp.foo_bar` or rename via `const { foo_bar: fooBar } = resp`. Instead, destructure as `const { foo_bar } = resp` keeping snake_case, or reference `resp.foo_bar` directly.
  - **Reasons**: (1) variable names match the orval-generated types for easier grep, (2) eliminates the maintenance cost and conversion-bug risk of a translation layer, (3) snake_case itself becomes a visual hint that the data comes from the server (distinguishing from UI-layer camelCase)
  - Variables and functions you declare yourself remain camelCase (standard JS/TS convention)
  - Values derived from server responses (e.g., aggregated results) should be camelCase (e.g., `const lossRate = total > 0 ? loss_count / total : 0`)
  - Biome's `useNamingConvention` does not inspect property names by default, which is consistent with this policy

## Hook / Variable Ordering in Routes and Components

Inside a route/component, hooks and variables are ordered by the following sections. Skip sections that don't apply. Section dividers are a single-line `// --- XX ---` comment (no separator lines).

1. **Routing** — `useNavigate`, `useParams`
2. **Server state** — TanStack Query (`useFiles`, `useConfig`, etc.) and values derived from them (`useMemo`)
3. **Streaming / subscription** — SSE (`useTopicsStream`, `useJobsStream`, etc.)
4. **Side effects** — `useEffect` (any required `useRef` setup goes in this section)
5. **Event handlers** — Define here only handlers that are used in multiple places, are memoized with `useCallback`, or have a long body. Inline single-use, non-memoized, short handlers into the JSX.
6. **Render-only state** — store selects used only in JSX (`leftOpen` / `isRecording`, etc.)

Within a section, group items "just before their use site". When the ordering rules need updating or a new section needs to be added, edit this section.

## Inlining Policy (TypeScript / React)

When a short, descriptive variable or event handler is used in only one place, inline it at the point of use. This removes the burden of tracking "which variable corresponds to which logic" separately from the JSX, and the actual behavior can be read directly at the usage site.

### Inlining descriptive variables

If the expression is short enough (roughly one line) and the variable name carries no more information than the expression itself, embed it directly in the JSX.

```tsx
// ❌ Simple derived value that adds no information beyond the expression
const someChecked = checkedFolders.size > 0;
return <Button disabled={!someChecked}>...</Button>;

// ✅ The logic is readable directly from the JSX
return <Button disabled={checkedFolders.size === 0}>...</Button>;
```

**Exceptions (keep the variable)**:
- Used in two or more places (deduplication)
- The expression is long or spans multiple lines
- A name clearly improves JSX readability

### Inlining event handlers

Inline a handler as an arrow function directly in the JSX prop when *all* of the following hold:

- It is used in only one place
- It is not memoized with `useCallback` / `useMemo` (a new function is created on every render anyway)
- The function body is short (roughly within 10 lines)
- It is not passed to a `React.memo`'d component (so memo invalidation is not a concern)

```tsx
// ❌ Trigger and logic are separated; you're just passing a re-created function via a name
const handleFilterChange = (newFilter: FilterKey) => {
  setCheckedFolders(newFilter === "all" ? [] : matchedFolders(newFilter));
  setFilter(newFilter);
};
return <FilterTabs onFilterChange={handleFilterChange} />;

// ✅ The logic is readable next to the trigger
return (
  <FilterTabs
    onFilterChange={(newFilter) => {
      setCheckedFolders(newFilter === "all" ? [] : matchedFolders(newFilter));
      setFilter(newFilter);
    }}
  />
);
```

**Do not inline**:
- Memoized with `useCallback` (memoization is intentionally required)
- Used in multiple places (avoid duplication)
- Long body (e.g., over 15 lines) that makes the JSX hard to read
- Passed to a `React.memo`'d child where reference stability is required to preserve memoization

### Branch inside the argument (instead of if/else)

When the same setter / function is called with only different arguments depending on a condition, use a ternary to "branch inside the argument". It makes "what changes" obvious at a glance.

```tsx
// ❌ Same setter repeated in both branches
if (newFilter === "all") {
  setCheckedFolders([]);
} else {
  setCheckedFolders(matched.map((r) => r.folder));
}

// ✅ Makes it explicit that only the argument changes
setCheckedFolders(
  newFilter === "all" ? [] : matched.map((r) => r.folder),
);
```

## CSS / Tailwind

- Use Tailwind v4 utility classes
- Keep custom CSS to a minimum
- Data-attribute selectors: `data-resize-handle-active:bg-ring` (v4 syntax)
