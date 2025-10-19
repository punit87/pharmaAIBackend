# Docker Image Build Automation

This repository contains a single GitHub Actions workflow to automatically build and publish Docker images for RAG-Anything and Docling projects to GitHub Container Registry.

## 🚀 Features

- **Single workflow** builds both images simultaneously
- **Uses original Dockerfiles** from source repositories
- **Multi-platform support** (linux/amd64, linux/arm64)
- **GitHub Container Registry** integration
- **Manual trigger** support with custom tags
- **Automatic caching** for faster builds

## 📦 Published Images

### RAG-Anything
- **Registry**: `ghcr.io/punit87/rag-anything`
- **Source**: [punit87/RAG-Anything](https://github.com/punit87/RAG-Anything)
- **Features**: All-in-One RAG Framework with multimodal support

### Docling
- **Registry**: `ghcr.io/punit87/docling`
- **Source**: [punit87/docling](https://github.com/punit87/docling)
- **Features**: Document parsing and processing

## 🔧 Workflow

### Single Deploy Workflow

- **`deploy.yml`**: Builds both RAG-Anything and Docling images using their original Dockerfiles

## 🚀 Usage

### Pull and Run Images

```bash
# Pull RAG-Anything image
docker pull ghcr.io/punit87/rag-anything:latest

# Pull Docling image
docker pull ghcr.io/punit87/docling:latest

# Run RAG-Anything container
docker run -it --rm \
  -v $(pwd)/documents:/app/documents \
  -e OPENAI_API_KEY=your_api_key \
  ghcr.io/punit87/rag-anything:latest

# Run Docling container
docker run -it --rm \
  -v $(pwd)/documents:/app/documents \
  ghcr.io/punit87/docling:latest
```

### Using Specific Tags

```bash
# Use a specific version
docker pull ghcr.io/punit87/rag-anything:v1.0.0

# Use a branch-specific tag
docker pull ghcr.io/punit87/rag-anything:develop
```

## 🔐 Authentication

To pull from GitHub Container Registry, you need to authenticate:

```bash
# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# Or use GitHub CLI
gh auth token | docker login ghcr.io -u YOUR_USERNAME --password-stdin
```

## 🛠️ Setup Instructions

### 1. Fork and Configure

1. Fork this repository
2. Go to your repository's **Settings** → **Actions** → **General**
3. Ensure "Workflow permissions" is set to "Read and write permissions"
4. Enable "Allow GitHub Actions to create and approve pull requests"

### 2. Repository Access

The workflows automatically check out the source repositories:
- `punit87/RAG-Anything`
- `punit87/docling`

Make sure these repositories are accessible and contain Dockerfiles.

### 2. Manual Trigger

You can manually trigger builds with custom tags:

1. Go to **Actions** tab in your repository
2. Select "Deploy Docker Images"
3. Click "Run workflow"
4. Enter a custom tag (optional)
5. Click "Run workflow"

## 📋 Available Tags

Images are tagged with:
- `latest` - Latest stable version
- `main` - Latest from main branch
- `develop` - Latest from develop branch
- `v1.0.0` - Semantic version tags
- Custom tags from manual triggers

## 🔄 Build Triggers

- **Automatic builds** on push to main/develop branches
- **PR builds** for testing changes
- **Manual builds** with custom tags

## 🏗️ Build Process

1. **Setup Docker Buildx** for multi-platform builds
2. **Login** to GitHub Container Registry
3. **Build RAG-Anything** using its Dockerfile from GitHub
4. **Build Docling** using its Dockerfile from GitHub
5. **Push both images** to GitHub Container Registry
6. **Generate summary** with image tags and usage instructions

## 📊 Monitoring

- Check the **Actions** tab for build status
- View build logs for debugging
- Monitor image sizes and build times
- Set up notifications for build failures

## 🐛 Troubleshooting

### Common Issues

1. **Permission denied**: Ensure workflow has write permissions
2. **Repository not found**: Check if source repositories exist and are accessible
3. **Build failures**: Check Dockerfile exists in source repositories
4. **Registry login failed**: Verify GITHUB_TOKEN permissions

### Debug Steps

1. Check workflow logs in Actions tab
2. Verify source repository accessibility
3. Test Dockerfile locally
4. Check GitHub Container Registry permissions

## 📚 Related Projects

- [RAG-Anything](https://github.com/punit87/RAG-Anything) - All-in-One RAG Framework
- [Docling](https://github.com/punit87/docling) - Document parsing library
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test the workflows
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Note**: This automation uses the existing Dockerfiles from the source repositories. No additional dependencies are installed in the GitHub Actions workflows - all dependencies are handled by the projects' own Dockerfiles and requirements files.
