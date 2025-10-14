-- Script d'initialisation de la base de données PostgreSQL pour le Bot Discord
-- Exécute ce script pour créer la base de données et les tables nécessaires

-- Créer la base de données (à exécuter en tant que superuser)
-- CREATE DATABASE discord_bot;

-- Se connecter à la base de données discord_bot avant d'exécuter le reste

-- Créer la table users pour le système de niveau/XP
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index pour améliorer les performances des requêtes de classement
CREATE INDEX IF NOT EXISTS idx_users_level_xp ON users (level DESC, xp DESC);

-- Fonction pour mettre à jour automatiquement updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger pour mettre à jour updated_at automatiquement
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Afficher les informations
SELECT 'Base de données initialisée avec succès!' AS status;
SELECT 'Table users créée avec ' || COUNT(*) || ' utilisateurs' AS info FROM users;
