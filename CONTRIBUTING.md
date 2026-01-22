# Contributing to Learning Connection Time

Thank you for your interest in contributing to this educational equity research project. This document provides guidelines for contributing.

## Ways to Contribute

### Report Issues
- **Bug reports**: Something not working as expected
- **Data quality issues**: Discrepancies in district data or calculations
- **Documentation improvements**: Typos, unclear explanations, missing information

### Suggest Enhancements
- New data sources (state education agencies, additional federal datasets)
- Methodology improvements for LCT calculations
- Visualization or reporting features

### Submit Code
- Bug fixes
- New state integrations (SEA data)
- Bell schedule enrichment for additional districts
- Test coverage improvements

## Development Setup

```bash
# Clone the repository
git clone https://github.com/your-username/learning-connection-time.git
cd learning-connection-time

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL database
docker-compose up -d

# Run tests to verify setup
pytest tests/ -v
```

## Code Standards

### Python Style
- Follow PEP 8 guidelines
- Use type hints where helpful
- Include docstrings for public functions
- Use `logging` instead of `print` statements

### Testing
- Add tests for new functionality
- Run the full test suite before submitting: `pytest tests/ -v`
- Maintain or improve test coverage

### Commits
- Use clear, descriptive commit messages
- One logical change per commit
- Reference issue numbers when applicable

## Pull Request Process

1. **Fork** the repository and create a feature branch
2. **Make changes** following the code standards above
3. **Add tests** for any new functionality
4. **Run tests** locally: `pytest tests/ -v`
5. **Update documentation** if needed
6. **Submit PR** with a clear description of changes

### PR Title Format
- `fix: description` for bug fixes
- `feat: description` for new features
- `docs: description` for documentation changes
- `test: description` for test additions/changes

## Adding a New State Integration

See [docs/SEA_INTEGRATION_GUIDE.md](docs/SEA_INTEGRATION_GUIDE.md) for detailed instructions on adding state education agency data integrations.

Quick overview:
1. Obtain state data files (enrollment, staffing, SPED)
2. Create crosswalk mapping state IDs to NCES LEAIDs
3. Write import script in `infrastructure/database/migrations/`
4. Create integration tests in `tests/test_{state}_integration.py`

## Questions?

Open an issue with the "question" label for any questions about contributing.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
