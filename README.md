# Chata Games - Master Repository

Welcome to the Chata Games master repository! This is a central hub for all games developed by the Chata Games organization.

## 📋 Repository Structure

This repository uses Git submodules to manage all game projects. Each game is a separate repository linked as a submodule.

```
chata-games/
├── trolluv-sklep/        # Shopping adventure game with troll theme
├── unikovka/             # Unique adventure with magical creatures
├── daligame/             # Artistic puzzle game inspired by surrealism
├── forest-rescue/        # Help rescue animals in the enchanted forest
├── grunts-way-home/      # Epic journey home game
├── tvojekariera/         # Career building strategy game
├── index.html            # Landing page with game links
└── README.md             # This file
```

## 🎮 Games

| Game | Description | Repository |
|------|-------------|------------|
| 🛍️ Trolluv Sklep | Shopping adventure with troll theme | [trolluv-sklep](https://github.com/chata-games/trolluv-sklep) |
| 🦄 Unikovka | Magical adventure game | [unikovka](https://github.com/chata-games/unikovka) |
| 🎨 Dali Game | Artistic puzzle game | [daligame](https://github.com/chata-games/daligame) |
| 🌲 Forest Rescue | Rescue animals in the forest | [forest-rescue](https://github.com/chata-games/forest-rescue) |
| 👹 Grunts Way Home | Epic journey adventure | [grunts-way-home](https://github.com/chata-games/grunts-way-home) |
| 💼 Tvojekariera | Career building strategy game | [tvojekariera](https://github.com/chata-games/tvojekariera) |

## 🚀 Getting Started

### Clone the Repository with Submodules

To clone this repository and all its submodules:

```bash
git clone --recurse-submodules https://github.com/chata-games/chata-games.git
cd chata-games
```

If you've already cloned the repository without submodules, initialize them:

```bash
git submodule update --init --recursive
```

### Update Submodules

To update all submodules to their latest commits:

```bash
git submodule update --remote --merge
```

Or update a specific submodule:

```bash
cd <game-name>
git pull origin main
```

## 📖 Development Guide

### Working with a Specific Game

Each game is a self-contained project. To work on a specific game:

1. Navigate to the game directory:
   ```bash
   cd trolluv-sklep
   ```

2. Follow the game's own README for setup and development instructions

3. Make changes and commit to that game's repository

### Adding a New Game

To add a new game to this collection:

1. Create the game repository in the chata-games organization on GitHub

2. Add it as a submodule to this master repository:
   ```bash
   git submodule add https://github.com/chata-games/<new-game>.git <new-game>
   ```

3. Update the landing page (`index.html`) and this README with the new game information

4. Commit the changes:
   ```bash
   git add .
   git commit -m "Add <new-game> to collection"
   git push origin main
   ```

### Updating the Landing Page

The `index.html` file contains the landing page for all games. To add a new game to the page:

1. Add a new game card in the `<div class="games-grid">` section
2. Follow the existing card structure with appropriate links and descriptions
3. Commit and push changes

## 🛠️ Master Repo Features

This master repository can be used to:

- **Coordinate development** across all games
- **Run coding agents** against all projects simultaneously
- **Track issues** and progress across multiple games
- **Manage CI/CD** for all games from a central location
- **Serve the landing page** showing all available games
- **Maintain unified documentation** and standards

## 📝 Contributing

Each game has its own contribution guidelines. Please refer to the individual game repositories for specific contribution instructions.

## 📄 License

Each game may have its own license. Please check individual game repositories for license information.

## 🤝 Support

For issues related to:
- **Specific games**: Check the individual game repository's issues
- **Master repository**: Open an issue in this repository
- **Landing page**: Contact the maintainers

## 📚 Additional Resources

- [Chata Games Organization](https://github.com/chata-games)
- [Landing Page](index.html)

---

**Last Updated**: 2026-07-12
