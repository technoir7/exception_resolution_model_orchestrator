-- Initialize database with required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create schema
CREATE SCHEMA IF NOT EXISTS ap;
