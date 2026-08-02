# XAML Code Map Guidelines

## File Header Format

```markdown
### [Window/UserControl/ResourceDictionary Name]
**Path**: `path/to/View.xaml` - [line count] lines
**Purpose**: [Brief description]
**Language**: XAML
**Code-behind**: `path/to/View.xaml.cs`
**Type**: Window | UserControl | Page | ResourceDictionary
```

## Documentation Structure

### For Windows and UserControls

```markdown
### MainWindow
**Path**: `Views/MainWindow.xaml` - 350 lines
**Purpose**: Primary application window
**Language**: XAML
**Code-behind**: `Views/MainWindow.xaml.cs`
**Type**: Window
**ViewModel**: MainViewModel (if MVVM)

#### Root Element
| Property | Value | Description |
|----------|-------|-------------|
| x:Class | MyApp.Views.MainWindow | Code-behind class |
| xmlns | Standard WPF namespaces | Namespace declarations |
| Title | "My Application" | Window title |
| Width | 1200 | Initial width |
| Height | 800 | Initial height |

#### Named Elements
| Name (x:Name) | Line | Type | Purpose |
|---------------|------|------|---------|
| MainGrid | 15 | Grid | Root layout container |
| MenuBar | 20 | Menu | Application menu |
| ContentArea | 45 | ContentControl | Main content region |
| StatusBar | 300 | StatusBar | Status display |
| DataGridMain | 150 | DataGrid | Primary data display |

#### Data Bindings
| Element | Line | Property | Binding Path | Mode | Description |
|---------|------|----------|--------------|------|-------------|
| TextBlock | 75 | Text | Title | OneWay | Window title |
| TextBox | 100 | Text | UserName | TwoWay | User input |
| Button | 125 | Command | SaveCommand | OneWay | Save action |
| DataGrid | 150 | ItemsSource | Items | OneWay | Data collection |
| CheckBox | 200 | IsChecked | IsEnabled | TwoWay | Toggle state |

#### Resources
| Key | Line | Type | Description |
|-----|------|------|-------------|
| PrimaryBrush | 8 | SolidColorBrush | Primary color |
| HeaderStyle | 12 | Style (TextBlock) | Header text style |
| ButtonTemplate | 25 | ControlTemplate | Custom button |
| DataTemplate1 | 50 | DataTemplate | Item template |

#### Event Handlers (Code-behind)
| Element | Line | Event | Handler | Description |
|---------|------|-------|---------|-------------|
| Button | 125 | Click | SaveButton_Click | Save handler |
| Window | 5 | Loaded | Window_Loaded | Init handler |
| DataGrid | 150 | SelectionChanged | DataGrid_SelectionChanged | Selection handler |
```

### For ResourceDictionaries

```markdown
### Styles.xaml
**Path**: `Resources/Styles.xaml` - 500 lines
**Purpose**: Application-wide styles and templates
**Language**: XAML
**Type**: ResourceDictionary
**Merged In**: App.xaml

#### Brushes and Colors
| Key | Line | Type | Value | Description |
|-----|------|------|-------|-------------|
| PrimaryColor | 10 | Color | #FF0078D7 | Primary brand color |
| PrimaryBrush | 11 | SolidColorBrush | StaticResource PrimaryColor | Primary brush |
| AccentBrush | 15 | LinearGradientBrush | Gradient definition | Accent gradient |

#### Styles
| Key | Line | TargetType | BasedOn | Description |
|-----|------|------------|---------|-------------|
| BaseButtonStyle | 50 | Button | - | Base button style |
| PrimaryButton | 100 | Button | BaseButtonStyle | Primary action button |
| HeaderTextStyle | 150 | TextBlock | - | Header text |
| DataGridStyle | 200 | DataGrid | - | Grid appearance |

#### Control Templates
| Key | Line | TargetType | Complexity | Description |
|-----|------|------------|------------|-------------|
| CustomButtonTemplate | 250 | Button | High | Custom button chrome |
| RoundedBorder | 300 | Border | Low | Rounded border template |
| LoadingSpinner | 350 | Control | Medium | Loading animation |

#### Data Templates
| Key | Line | DataType | Description |
|-----|------|----------|-------------|
| UserItemTemplate | 400 | UserModel | User list item |
| ProductTemplate | 450 | ProductModel | Product display |
```

## XAML-Specific Patterns to Document

### 1. Layout Containers

Document the layout structure:
```markdown
#### Layout Hierarchy
```
Grid (MainGrid)
├── DockPanel (TopSection)
│   ├── Menu (DockPanel.Dock="Top")
│   └── ToolBar (DockPanel.Dock="Top")
├── Grid.Row="1" (ContentArea)
│   ├── Grid.Column="0" - Navigation (TreeView)
│   ├── GridSplitter (Grid.Column="1")
│   └── Grid.Column="2" - Main Content
└── Grid.Row="2" (StatusBar)
```
```

### 2. Triggers and Animations

```markdown
#### Triggers
| Element | Line | Trigger Type | Condition | Action |
|---------|------|--------------|-----------|--------|
| Button | 125 | Property | IsMouseOver=True | Change background |
| DataGrid | 200 | Event | Loaded | Begin animation |
| TextBox | 250 | Data | Validation.HasError=True | Show error border |

#### Storyboards
| Name | Line | Target | Duration | Description |
|------|------|--------|----------|-------------|
| FadeInAnimation | 300 | Opacity | 0:0:0.5 | Fade in effect |
| SlideAnimation | 350 | TranslateTransform | 0:0:0.3 | Slide transition |
```

### 3. Value Converters

```markdown
#### Value Converters (Referenced)
| Key | Line | Type | Converts From | Converts To | Description |
|-----|------|------|---------------|-------------|-------------|
| BoolToVisibility | 15 | BooleanToVisibilityConverter | bool | Visibility | Show/hide based on bool |
| NullToVisibility | 18 | NullToVisibilityConverter | object | Visibility | Show if not null |
| DateFormatter | 22 | DateFormatConverter | DateTime | string | Format date display |
```

### 4. Attached Properties

```markdown
#### Attached Properties Usage
| Element | Line | Property | Value | Description |
|---------|------|----------|-------|-------------|
| Button | 100 | Grid.Row | 1 | Grid row placement |
| TextBlock | 125 | DockPanel.Dock | Top | Dock position |
| Control | 150 | Validation.ErrorTemplate | {...} | Custom error display |
| Element | 175 | local:CustomBehavior.IsEnabled | True | Custom behavior |
```

### 5. MVVM Bindings

```markdown
#### MVVM Bindings Summary
| Pattern | Count | Lines | Description |
|---------|-------|-------|-------------|
| Command bindings | 15 | Various | Button/menu commands |
| TwoWay property | 25 | Various | User input fields |
| OneWay display | 50 | Various | Read-only data display |
| ObservableCollection | 8 | Various | Dynamic lists |
| INotifyPropertyChanged | All | - | Property change notifications |
```

### 6. Custom Controls and Behaviors

```markdown
#### Custom Controls
| Control | Line | Namespace | Description |
|---------|------|-----------|-------------|
| ColorPicker | 200 | local:ColorPicker | Custom color picker |
| NumericUpDown | 250 | local:NumericUpDown | Numeric input |

#### Behaviors (Blend SDK / Custom)
| Behavior | Line | Target | Description |
|----------|------|--------|-------------|
| EventTrigger | 300 | Button | Event-to-command |
| DragDropBehavior | 350 | ListBox | Drag-drop support |
```

## Common XAML Patterns

### 1. Grid Definitions

Document complex grid structures:
```markdown
#### Grid Structure (MainGrid)
**Row Definitions**:
- Row 0 (Auto): Menu and toolbar
- Row 1 (*): Main content area
- Row 2 (Auto): Status bar

**Column Definitions**:
- Column 0 (200): Navigation panel
- Column 1 (Auto): Splitter
- Column 2 (*): Main content
```

### 2. Style Inheritance

```markdown
#### Style Hierarchy
```
BaseControlStyle
├── BaseButtonStyle
│   ├── PrimaryButton
│   ├── SecondaryButton
│   └── DangerButton
└── BaseTextStyle
    ├── HeaderStyle
    └── BodyStyle
```
```

### 3. Resource Merging

```markdown
#### Merged Dictionaries
| Source | Line | Purpose |
|--------|------|---------|
| Colors.xaml | 5 | Color definitions |
| Brushes.xaml | 6 | Brush resources |
| Styles.xaml | 7 | Control styles |
| Templates.xaml | 8 | Control templates |
```

### 4. Data Templates and Selectors

```markdown
#### Data Template Selectors
| Selector | Line | Templates | Selection Logic |
|----------|------|-----------|-----------------|
| ItemTemplateSelector | 400 | UserTemplate, AdminTemplate | Based on user role |
| StatusTemplateSelector | 450 | ActiveTemplate, InactiveTemplate | Based on status |
```

## Performance Considerations

Document these XAML performance patterns:
- **Virtualization**: `VirtualizingStackPanel.IsVirtualizing="True"`
- **UI Virtualization**: DataGrid/ListBox virtualization settings
- **Deferred loading**: `x:Load="False"` for conditional UI
- **Resource freezing**: Frozen brushes and geometries
- **Hardware acceleration**: `RenderOptions.BitmapScalingMode`

## XAML Namespaces

Document all namespace declarations:
```markdown
#### Namespace Declarations
| Prefix | Line | URI | Purpose |
|--------|------|-----|---------|
| (default) | 3 | presentation | WPF core |
| x | 3 | xaml | XAML language |
| d | 4 | expression/blend | Design-time |
| mc | 4 | markup-compatibility | Markup compatibility |
| local | 5 | clr-namespace:MyApp | Local types |
| vm | 6 | clr-namespace:MyApp.ViewModels | ViewModels |
| sys | 7 | clr-namespace:System;assembly=mscorlib | System types |
```

## Design-Time Features

```markdown
#### Design-Time Data
| Element | Line | Property | Value | Purpose |
|---------|------|----------|-------|---------|
| Window | 3 | d:DataContext | {...} | Design-time ViewModel |
| ItemsControl | 100 | d:ItemsSource | {...} | Sample data |
| TextBlock | 150 | d:Text | "Sample" | Design placeholder |
```

## Validation and Error Templates

```markdown
#### Validation
| Element | Line | Validation Rules | Error Template |
|---------|------|------------------|----------------|
| TextBox | 100 | RequiredRule, RegexRule | Line 105 |
| ComboBox | 150 | NotNullRule | Default |
```
