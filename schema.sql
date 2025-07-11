-- real_estate_ai

DROP TABLE IF EXISTS `site`;

CREATE TABLE `site` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `url` varchar(255) NOT NULL,
  `floorplans_url` varchar(255),
  `first_visit` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `deals` text,
  `amenities` text,
  `state` varchar(255),
  `address` varchar(255),
  `container_selector` varchar(255),
  `listing_count` int,
  `region` varchar(255),
  PRIMARY KEY (`id`)
);

DROP TABLE IF EXISTS `property`;

CREATE TABLE `property` (
  `id` int NOT NULL AUTO_INCREMENT,
  `site_id` int NOT NULL,
  `floorplans_url` varchar(255),
  `title` varchar(255),
  `amenities` text,
  `address` varchar(255),
  `container_selector` varchar(255),
  `listing_count` int,
  PRIMARY KEY (`id`),
  KEY `site_id` (`site_id`),
  CONSTRAINT `property_ibfk_1` FOREIGN KEY (`site_id`) REFERENCES `site` (`id`) ON DELETE CASCADE
);

DROP TABLE IF EXISTS `listing`;

CREATE TABLE `listing` (
  `id` int NOT NULL AUTO_INCREMENT,
  `site_id` int NOT NULL,
  `property_id` int DEFAULT NULL,
  `listname` varchar(255) NOT NULL,
  `bedrooms` int(1),
  `bathrooms`int(1),
  `sqft` varchar(255) DEFAULT NULL,
  `shared_room` tinyint(1) DEFAULT NULL,
  `amenities` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_listing` (`site_id`,`listname`),
  KEY `property_id` (`property_id`),
  CONSTRAINT `listing_ibfk_2` FOREIGN KEY (`property_id`) REFERENCES `property` (`id`) ON DELETE CASCADE,
  CONSTRAINT `listing_ibfk_3` FOREIGN KEY (`site_id`) REFERENCES `site` (`id`) ON DELETE CASCADE
);

DROP TABLE IF EXISTS `listing_snapshot`;

CREATE TABLE `listing_snapshot` (
  `id` int NOT NULL AUTO_INCREMENT,
  `listing_id` int NOT NULL,
  `time_checked` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `availability` varchar(255) DEFAULT NULL,
  `price_low` varchar(255) DEFAULT NULL,
  `price_high` varchar(255) DEFAULT NULL,
  `pre_deal_price` varchar(255) DEFAULT NULL,
  `deals` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `listing_id` (`listing_id`),
  CONSTRAINT `listing_snapshot_ibfk_1` FOREIGN KEY (`listing_id`) REFERENCES `listing` (`id`) ON DELETE CASCADE
);
