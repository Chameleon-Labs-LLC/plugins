# C# Code Map Guidelines

## File Header Format

```markdown
### [Class/Namespace Name]
**Path**: `path/to/File.cs` - [line count] lines
**Purpose**: [Brief description]
**Language**: C#
**Namespace**: [Full.Namespace.Path]
```

## Documentation Structure

### For Classes

#### Class Header
```markdown
### ClassName
**Path**: `Services/DataService.cs` - 450 lines
**Purpose**: Handles data persistence and caching
**Language**: C#
**Namespace**: MyApp.Services
**Inheritance**: BaseService → IDataService
**Attributes**: [ServiceLifetime.Singleton], [Export(typeof(IDataService))]
```

#### Properties Table
```markdown
#### Properties
| Property | Line | Type | Access | Auto | Description |
|----------|------|------|--------|------|-------------|
| ConnectionString | 45 | string | public | Yes | Database connection |
| _cache | 47 | Dictionary<string,object> | private | No | Internal cache |
| IsConnected | 50 | bool | public | Yes, get-only | Connection status |
| Data { get; set; } | 52 | DataModel | public | Yes | Auto-property |
| Count { get; } | 55 | int | public | Computed | Cache item count |
```

#### Methods Table
```markdown
#### Methods
| Method | Line | Access | Returns | Async | Generic | Description |
|--------|------|--------|---------|-------|---------|-------------|
| Initialize | 100 | public | void | No | No | Setup method |
| GetDataAsync | 125 | public | Task<Data> | Yes | No | Async data retrieval |
| ProcessAsync<T> | 150 | public | Task<T> | Yes | Yes | Generic processor |
| Dispose | 200 | public | void | No | No | IDisposable cleanup |
| ValidateInput | 225 | private | bool | No | No | Input validation |
| OnPropertyChanged | 250 | protected | void | No | No | Property change notification |
```

#### Events Table
```markdown
#### Events
| Event | Line | Type | Description |
|-------|------|------|-------------|
| DataChanged | 60 | EventHandler<DataEventArgs> | Fires when data changes |
| PropertyChanged | 63 | PropertyChangedEventHandler | INotifyPropertyChanged implementation |
| ErrorOccurred | 65 | EventHandler<ErrorEventArgs> | Error notification |
```

#### Constructors Table
```markdown
#### Constructors
| Constructor | Line | Parameters | Description |
|-------------|------|------------|-------------|
| ClassName() | 75 | none | Default constructor |
| ClassName(ILogger logger) | 82 | ILogger | DI constructor |
| ClassName(string config) | 90 | string | Configuration constructor |
```

### For Interfaces

```markdown
### IDataService
**Path**: `Interfaces/IDataService.cs` - 85 lines
**Purpose**: Data service contract
**Language**: C#
**Namespace**: MyApp.Interfaces

#### Interface Members
| Member | Line | Type | Returns | Description |
|--------|------|------|---------|-------------|
| GetData | 12 | Method | Task<Data> | Data retrieval contract |
| SaveData | 18 | Method | Task<bool> | Data persistence contract |
| DataChanged | 24 | Event | EventHandler | Change notification contract |
| Count | 30 | Property | int | Item count accessor |
```

### For Enums

```markdown
### Status (Enum)
**Path**: `Models/Status.cs` - 15 lines
**Language**: C#
**Namespace**: MyApp.Models

#### Enum Values
| Value | Numeric | Line | Description |
|-------|---------|------|-------------|
| None | 0 | 10 | Default/unset |
| Active | 1 | 11 | Active status |
| Inactive | 2 | 12 | Inactive status |
| Error | 99 | 13 | Error state |
```

### For Structs and Records

```markdown
### Point (Struct)
**Path**: `Models/Point.cs` - 45 lines
**Language**: C#
**Type**: readonly struct

#### Fields/Properties
| Member | Line | Type | Readonly | Description |
|--------|------|------|----------|-------------|
| X | 10 | double | Yes | X coordinate |
| Y | 11 | double | Yes | Y coordinate |

---

### UserRecord (Record)
**Path**: `Models/UserRecord.cs` - 20 lines
**Language**: C#
**Type**: record class

#### Record Members
| Member | Line | Type | Init-only | Description |
|--------|------|------|-----------|-------------|
| Id | 8 | int | Yes | User identifier |
| Name | 9 | string | Yes | User name |
| Email | 10 | string | Yes | Email address |
```

## C#-Specific Patterns to Document

### 1. Properties

Distinguish between:
- **Auto-properties**: `public string Name { get; set; }`
- **Computed properties**: `public int Count => items.Count;`
- **Properties with backing fields**: Full implementation with private field
- **Init-only**: `public string Name { get; init; }`
- **Required**: `public required string Name { get; set; }`

### 2. Async Patterns

```markdown
| Method | Line | Returns | Async Pattern |
|--------|------|---------|---------------|
| ProcessAsync | 100 | Task<Result> | Task-based async |
| StreamDataAsync | 125 | IAsyncEnumerable<Item> | Async enumerable |
| GetAwaiter | 150 | TaskAwaiter<T> | Custom awaitable |
```

### 3. Generics

```markdown
| Method/Class | Line | Generic Constraints | Description |
|--------------|------|---------------------|-------------|
| Process<T> | 75 | where T : class, new() | Generic with constraints |
| Cache<TKey, TValue> | 100 | where TKey : notnull | Generic class |
```

### 4. LINQ and Query Expressions

Document files/methods using LINQ heavily:
```markdown
**LINQ Usage**:
- Line 145-160: Complex query with joins and grouping
- Line 200-210: Parallel LINQ for performance
```

### 5. Events and Delegates

```markdown
#### Delegates
| Delegate | Line | Signature | Description |
|----------|------|-----------|-------------|
| DataProcessor | 25 | void (Data data) | Data processing callback |
| Validator<T> | 30 | bool (T item) | Generic validation |

#### Events
| Event | Line | Delegate Type | Description |
|-------|------|---------------|-------------|
| ItemAdded | 45 | EventHandler<ItemEventArgs> | Item addition notification |
```

### 6. Extension Methods

```markdown
### StringExtensions
**Path**: `Extensions/StringExtensions.cs`
**Purpose**: String utility extensions

#### Extension Methods
| Method | Line | Extends | Returns | Description |
|--------|------|---------|---------|-------------|
| ToTitleCase | 15 | string | string | Converts to title case |
| IsNullOrEmpty | 28 | string | bool | Null/empty check |
```

### 7. Attributes

Document custom attributes and their usage:
```markdown
#### Custom Attributes
| Attribute | Line | Target | Description |
|-----------|------|--------|-------------|
| [Validate] | 100 | Method | Validation attribute |
| [Cache(Duration=60)] | 125 | Method | Caching directive |
```

## WPF-Specific Patterns

### For ViewModel Classes

```markdown
### MainViewModel
**Path**: `ViewModels/MainViewModel.cs`
**Language**: C#
**Pattern**: MVVM ViewModel
**Implements**: INotifyPropertyChanged

#### Bindable Properties
| Property | Line | Type | Notify | Command | Description |
|----------|------|------|--------|---------|-------------|
| Title | 45 | string | Yes | - | Window title |
| Items | 50 | ObservableCollection<Item> | Yes | - | Data collection |
| SelectedItem | 55 | Item | Yes | - | Current selection |

#### Commands
| Command | Line | Type | CanExecute | Description |
|---------|------|------|------------|-------------|
| SaveCommand | 100 | ICommand | Line 105 | Saves data |
| DeleteCommand | 120 | RelayCommand | Line 125 | Deletes item |
```

### For UserControls and Windows

```markdown
### MainWindow
**Path**: `Views/MainWindow.xaml.cs`
**Language**: C#
**UI Type**: Window
**XAML**: `Views/MainWindow.xaml`

#### Event Handlers
| Handler | Line | Event Source | Description |
|---------|------|--------------|-------------|
| OnLoaded | 45 | Window.Loaded | Initialization |
| Button_Click | 60 | Button.Click | Button handler |
| DataGrid_SelectionChanged | 75 | DataGrid.SelectionChanged | Selection handler |

#### Dependency Properties
| Property | Line | Type | Default | Description |
|----------|------|------|---------|-------------|
| ItemsSource | 100 | IEnumerable | null | Data source |
| SelectedValue | 115 | object | null | Selected item |
```

## .NET Specific Configuration Files

Document these C#/.NET config files:
- `*.csproj` - Project file (PackageReferences, PropertyGroups)
- `*.sln` - Solution file
- `app.config` / `web.config` - App configuration (legacy)
- `appsettings.json` - App settings (.NET Core/5+)
- `launchSettings.json` - Debug/launch profiles
- `Directory.Build.props` - MSBuild properties
- `nuget.config` - NuGet configuration

## Architecture Patterns Common in C#

Document these when found:
- **Dependency Injection**: Constructor injection, service registration
- **Repository Pattern**: Data access abstraction
- **Unit of Work**: Transaction management
- **MVVM**: Model-View-ViewModel separation (WPF/Xamarin)
- **MVC/Razor Pages**: ASP.NET patterns
- **Middleware**: ASP.NET Core middleware pipeline
- **Options Pattern**: `IOptions<T>` configuration

## Performance Patterns

Document these optimization patterns:
- **`Span<T>` / `Memory<T>`**: Zero-copy operations
- **`ValueTask<T>`**: Reduced allocations for async
- **`ArrayPool<T>`**: Array reuse
- **`StringBuilder`**: String concatenation
- **`struct` vs `class`**: Value type optimization
- **`readonly struct`**: Immutable value types
- **`in` parameters**: Passing by readonly reference

## Memory Management

Document IDisposable patterns:
```markdown
#### IDisposable Implementation
- **Dispose method**: Line 250
- **Dispose pattern**: Full pattern with finalizer
- **Using statements**: Lines 100, 125, 150 (scoped resource management)
- **Async disposal**: `IAsyncDisposable` at line 275
```
