# Phosphor Icons

This directory contains SVG icons from [Phosphor Icons](https://phosphoricons.com/) for the project tracker dashboard.

## Available Icons

All icons are available in two weights: **regular** and **bold**.

### Navigation & UI
- `house` / `house-bold` - Home/Dashboard
- `gear` / `gear-bold` - Settings
- `arrow-left` / `arrow-left-bold` - Navigate back
- `arrow-right` / `arrow-right-bold` - Navigate forward
- `caret-down` / `caret-down-bold` - Dropdown indicator
- `caret-up` / `caret-up-bold` - Collapse indicator

### Files & Folders
- `folder` / `folder-bold` - Single folder
- `folders` / `folders-bold` - Multiple folders
- `file` / `file-bold` - Single file
- `files` / `files-bold` - Multiple files

### Actions
- `plus` / `plus-bold` - Add/Create
- `minus` / `minus-bold` - Remove/Subtract
- `pencil` / `pencil-bold` - Edit
- `trash` / `trash-bold` - Delete
- `download` / `download-bold` - Download
- `upload` / `upload-bold` - Upload
- `magnifying-glass` / `magnifying-glass-bold` - Search

### Status & Feedback
- `check` / `check-bold` - Success/Checkmark
- `check-circle` / `check-circle-bold` - Success (circular)
- `x` / `x-bold` - Close/Cancel
- `x-circle` / `x-circle-bold` - Error/Cancel (circular)
- `warning` / `warning-bold` - Warning
- `warning-circle` / `warning-circle-bold` - Warning (circular)
- `info` / `info-bold` - Information

### View Options
- `list` / `list-bold` - List view
- `grid-four` / `grid-four-bold` - Grid view

### Theme
- `sun` / `sun-bold` - Light mode
- `moon` / `moon-bold` - Dark mode

### User
- `user` / `user-bold` - User profile/account

## Usage in HTML

```html
<!-- Regular weight -->
<img src="/static/icons/phosphor/gear.svg" alt="Settings" width="24" height="24">

<!-- Bold weight -->
<img src="/static/icons/phosphor/gear-bold.svg" alt="Settings" width="24" height="24">
```

## Usage in CSS

```css
.icon {
  width: 24px;
  height: 24px;
  background-image: url('/static/icons/phosphor/gear.svg');
  background-size: contain;
  background-repeat: no-repeat;
}
```

## License

Phosphor Icons are licensed under the MIT License.
See https://github.com/phosphor-icons/core for more information.
