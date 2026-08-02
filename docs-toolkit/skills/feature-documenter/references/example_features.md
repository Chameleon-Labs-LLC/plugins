# Example: ImageGen App Features

> Below is a worked example. "ImageGen" is a placeholder name — replace with your actual product when using this template.


> AI-powered image generation desktop application with multi-provider support.

## Core Features

### Image Generation
- **Text-to-Image** - Generate images from text prompts using AI models
- **Multi-Provider Support** - Switch between Google Gemini, OpenAI DALL-E, and Stability AI
- **Reference Images** - Use existing images to guide generation style
- **Batch Generation** - Generate multiple variations from a single prompt

### Prompt Enhancement
- **AI-Assisted Prompts** - Improve prompts automatically using LLM suggestions
- **Template System** - Save and reuse prompt templates with placeholders
- **Prompt History** - Access previously used prompts for quick reuse

### Output Management
- **Auto-Save** - Images automatically saved with descriptive filenames
- **Metadata Sidecars** - JSON files store generation parameters alongside images
- **Custom Output Directory** - Choose where generated images are saved

## Getting Started

1. Launch the application: `python main.py`
2. Enter your API key in Settings
3. Type a prompt and click Generate
4. Find your image in the output directory

## Feature Details

### Multi-Provider Support
Switch between AI providers without changing your workflow. Each provider has unique strengths - Gemini excels at photorealistic images while DALL-E offers strong artistic interpretation.
- Automatic model selection based on provider
- Provider-specific settings and defaults
- Unified interface across all providers

### Template System
Create reusable prompt templates for consistent results. Templates support placeholder substitution for dynamic content.
- Save frequently used prompt structures
- Variables like `{subject}`, `{style}` for customization
- Import/export templates for sharing

### Video Project Mode
Create lyric-synced video projects with AI-generated visuals for each scene.
- Timeline-based scene management
- Automatic scene prompts from lyrics
- Export to video formats

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| provider | AI provider to use | google |
| model | Specific model for generation | auto |
| output_dir | Where to save images | ~/ImageGen/output |
| save_metadata | Store generation params | true |

## Supported Formats/Integrations

- **Output Formats** - PNG, JPEG, WebP
- **Providers** - Google Gemini, OpenAI, Stability AI
- **Interfaces** - GUI (Qt), CLI
