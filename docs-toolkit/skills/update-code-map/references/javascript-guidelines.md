# JavaScript/TypeScript Code Map Guidelines

## File Header Format

```markdown
### [Module/Component Name]
**Path**: `path/to/module.js|ts` - [line count] lines
**Purpose**: [Brief description]
**Language**: JavaScript | TypeScript
**Module Type**: ESM | CommonJS | AMD
**Framework**: React | Vue | Angular | Node.js | Vanilla
```

## TypeScript-Specific Documentation

### For Classes

```markdown
### ServiceClass
**Path**: `services/data.service.ts` - 250 lines
**Purpose**: Data management service
**Language**: TypeScript

#### Properties
| Property | Line | Type | Access | Readonly | Description |
|----------|------|------|--------|----------|-------------|
| private _cache | 15 | Map<string, any> | private | No | Internal cache |
| public isReady | 18 | boolean | public | No | Ready state |
| readonly config | 20 | Config | public | Yes | Configuration |

#### Methods
| Method | Line | Access | Returns | Async | Generic | Description |
|--------|------|--------|---------|-------|---------|-------------|
| initialize | 50 | public | Promise<void> | Yes | No | Setup method |
| getData<T> | 75 | public | Promise<T> | Yes | Yes | Generic data fetch |
| private validateInput | 100 | private | boolean | No | No | Input validation |
```

### For Interfaces and Types

```markdown
### Interfaces
| Interface | Line | Extends | Properties | Description |
|-----------|------|---------|------------|-------------|
| IDataService | 10 | IBaseService | 5 | Service contract |
| IUser | 25 | - | 8 | User model |

### Type Aliases
| Type | Line | Definition | Description |
|------|------|------------|-------------|
| UserId | 50 | string \| number | User identifier |
| ApiResponse<T> | 55 | { data: T; error?: string } | API response wrapper |
| EventCallback | 60 | (event: Event) => void | Event handler type |
```

### For Enums

```markdown
### Enums
| Enum | Line | Type | Values | Description |
|------|------|------|--------|-------------|
| Status | 100 | string | Active, Inactive, Pending | Status states |
| ErrorCode | 110 | number | 0-5 | Error codes |
```

## JavaScript (ES6+) Documentation

### For Modules

```markdown
### dataModule
**Path**: `modules/data.js` - 180 lines
**Purpose**: Data manipulation utilities
**Language**: JavaScript (ES6+)
**Module Type**: ESM

#### Exports
| Export | Line | Type | Default | Description |
|--------|------|------|---------|-------------|
| processData | 50 | function | No | Data processor |
| DataManager | 100 | class | No | Manager class |
| config | 150 | object | No | Configuration |
| default | 175 | function | Yes | Default export |

#### Imports
| Import | Line | From | Type | Description |
|--------|------|------|------|-------------|
| { fetch } | 1 | node-fetch | Named | HTTP client |
| axios | 2 | axios | Default | HTTP library |
| * as utils | 3 | ./utils | Namespace | Utility functions |
```

### For Functions

```markdown
#### Functions
| Function | Line | Params | Returns | Async | Pure | Description |
|----------|------|--------|---------|-------|------|-------------|
| processData | 50 | (data: any[]) | any[] | No | Yes | Data transformation |
| async fetchUser | 75 | (id: string) | Promise<User> | Yes | No | User retrieval |
| createHandler | 100 | () => Function | Function | No | No | Handler factory |
| memoizedCalc | 125 | (n: number) | number | No | Yes | Memoized calculation |
```

## React-Specific Patterns

### For React Components

```markdown
### UserProfile
**Path**: `components/UserProfile.tsx` - 200 lines
**Purpose**: User profile display component
**Language**: TypeScript
**Framework**: React
**Type**: Functional Component

#### Props Interface
| Prop | Line | Type | Required | Default | Description |
|------|------|------|----------|---------|-------------|
| userId | 15 | string | Yes | - | User identifier |
| onUpdate | 16 | (user: User) => void | No | undefined | Update callback |
| showDetails | 17 | boolean | No | false | Show detailed view |

#### State (useState)
| State | Line | Type | Initial | Description |
|-------|------|------|---------|-------------|
| user | 25 | User \| null | null | User data |
| isLoading | 26 | boolean | false | Loading state |
| error | 27 | Error \| null | null | Error state |

#### Effects (useEffect)
| Effect | Line | Dependencies | Purpose |
|--------|------|--------------|---------|
| useEffect | 40 | [userId] | Fetch user data |
| useEffect | 60 | [user] | Update document title |
| useEffect | 75 | [] | Component mount setup |

#### Custom Hooks
| Hook | Line | Returns | Description |
|------|------|---------|-------------|
| useUserData | 100 | { user, loading, error } | User data hook |
| useDebounce | 125 | debouncedValue | Debounce hook |

#### Event Handlers
| Handler | Line | Event Type | Description |
|---------|------|------------|-------------|
| handleSubmit | 150 | FormEvent | Form submission |
| handleChange | 165 | ChangeEvent<Input> | Input change |
| handleClick | 180 | MouseEvent | Button click |
```

### For Redux/State Management

```markdown
### userSlice
**Path**: `store/userSlice.ts` - 150 lines
**Purpose**: User state management
**Language**: TypeScript
**Framework**: Redux Toolkit

#### State Shape
| Property | Line | Type | Initial | Description |
|----------|------|------|---------|-------------|
| users | 15 | User[] | [] | User list |
| currentUser | 16 | User \| null | null | Active user |
| loading | 17 | boolean | false | Loading state |

#### Reducers
| Reducer | Line | Action Payload | Description |
|---------|------|----------------|-------------|
| setUsers | 30 | User[] | Set user list |
| setCurrentUser | 40 | User | Set active user |
| clearUsers | 50 | void | Clear all users |

#### Async Thunks
| Thunk | Line | Args | Returns | Description |
|-------|------|------|---------|-------------|
| fetchUsers | 75 | void | Promise<User[]> | Fetch all users |
| updateUser | 100 | { id, data } | Promise<User> | Update user |

#### Selectors
| Selector | Line | Returns | Description |
|----------|------|---------|-------------|
| selectUsers | 125 | User[] | Get all users |
| selectCurrentUser | 130 | User \| null | Get current user |
```

## Node.js-Specific Patterns

### For Express Routes/Controllers

```markdown
### userController
**Path**: `controllers/userController.js` - 300 lines
**Purpose**: User API endpoints
**Language**: JavaScript
**Framework**: Express.js

#### Route Handlers
| Method | Line | Route | Middleware | Description |
|--------|------|-------|------------|-------------|
| GET | 50 | /api/users | auth | Get all users |
| GET | 75 | /api/users/:id | auth | Get user by ID |
| POST | 100 | /api/users | auth, validate | Create user |
| PUT | 150 | /api/users/:id | auth, validate | Update user |
| DELETE | 200 | /api/users/:id | auth, admin | Delete user |

#### Middleware
| Middleware | Line | Purpose |
|------------|------|---------|
| authenticate | 25 | JWT authentication |
| validateUser | 40 | Request validation |
| errorHandler | 275 | Error handling |
```

## Common JavaScript Patterns to Document

### 1. Closures and IIFEs

```markdown
**Closures**: Lines 50-75 (createCounter factory)
**IIFE**: Line 100 (module pattern)
```

### 2. Promises and Async/Await

```markdown
#### Async Patterns
| Function | Line | Pattern | Error Handling |
|----------|------|---------|----------------|
| fetchData | 50 | async/await | try-catch |
| loadUser | 75 | Promise chain | .catch() |
| parallel | 100 | Promise.all | try-catch |
```

### 3. Destructuring and Spread

```markdown
**Destructuring**: Lines 25, 50, 75 (parameter and object destructuring)
**Spread Operator**: Lines 100, 125 (object/array spreading)
```

### 4. Higher-Order Functions

```markdown
#### HOFs
| Function | Line | Type | Description |
|----------|------|------|-------------|
| withAuth | 100 | HOC | Authentication wrapper |
| compose | 125 | Utility | Function composition |
| memoize | 150 | Utility | Result memoization |
```

## Configuration Files

Document these JavaScript/TypeScript config files:
- `package.json` - Dependencies and scripts
- `tsconfig.json` - TypeScript configuration
- `webpack.config.js` - Webpack bundling
- `vite.config.ts` - Vite configuration
- `.eslintrc.js` / `eslint.config.js` - Linting rules
- `.prettierrc` - Code formatting
- `jest.config.js` - Testing configuration
- `babel.config.js` - Babel transpilation
- `next.config.js` - Next.js configuration
- `vue.config.js` - Vue CLI configuration

## Performance Patterns

Document these optimization patterns:
- **Memoization**: React.memo, useMemo, useCallback
- **Code splitting**: Dynamic imports, lazy loading
- **Debouncing/Throttling**: Event optimization
- **Virtual scrolling**: Large list handling
- **Web Workers**: Background processing
- **Service Workers**: Offline support, caching
