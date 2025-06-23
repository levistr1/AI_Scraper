#! /bin/bash

# Drop all tables
mysql -u root -pSummer2025! -e "DROP DATABASE IF EXISTS real_estate_ai"
mysql -u root -pSummer2025! -e "CREATE DATABASE real_estate_ai"
mysql -u root -pSummer2025! real_estate_ai < schema.sql
mysql -u root -pSummer2025! real_estate_ai < data.sql