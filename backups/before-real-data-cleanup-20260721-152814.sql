-- MySQL dump 10.13  Distrib 8.0.44, for Win64 (x86_64)
--
-- Host: 127.0.0.1    Database: socialflow
-- ------------------------------------------------------
-- Server version	8.0.44

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `account_activity_stat`
--

DROP TABLE IF EXISTS `account_activity_stat`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `account_activity_stat` (
  `id` int NOT NULL AUTO_INCREMENT,
  `account_id` int NOT NULL,
  `platform` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `day_of_week` int NOT NULL,
  `hour_of_day` int NOT NULL,
  `post_count` int NOT NULL,
  `avg_impressions` float NOT NULL,
  `avg_engagement_rate` float NOT NULL,
  `avg_likes` float NOT NULL,
  `avg_comments` float NOT NULL,
  `avg_collects` float NOT NULL,
  `avg_shares` float NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `account_id` (`account_id`),
  CONSTRAINT `account_activity_stat_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `platform_account` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `account_activity_stat`
--

LOCK TABLES `account_activity_stat` WRITE;
/*!40000 ALTER TABLE `account_activity_stat` DISABLE KEYS */;
/*!40000 ALTER TABLE `account_activity_stat` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `activity_prior`
--

DROP TABLE IF EXISTS `activity_prior`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `activity_prior` (
  `id` int NOT NULL AUTO_INCREMENT,
  `platform` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `day_of_week` int NOT NULL,
  `hour_of_day` int NOT NULL,
  `base_score` float NOT NULL,
  `source_description` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_activity_prior_slot` (`platform`,`day_of_week`,`hour_of_day`),
  KEY `ix_activity_prior_platform` (`platform`)
) ENGINE=InnoDB AUTO_INCREMENT=73 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `activity_prior`
--

LOCK TABLES `activity_prior` WRITE;
/*!40000 ALTER TABLE `activity_prior` DISABLE KEYS */;
INSERT INTO `activity_prior` VALUES (1,'WEIBO',0,0,42,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(2,'WEIBO',0,1,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(3,'WEIBO',0,2,48,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(4,'WEIBO',0,3,51,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(5,'WEIBO',0,4,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(6,'WEIBO',0,5,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(7,'WEIBO',0,6,42,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(8,'WEIBO',0,7,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(9,'WEIBO',0,8,78,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(10,'WEIBO',0,9,51,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(11,'WEIBO',0,10,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(12,'WEIBO',0,11,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(13,'WEIBO',0,12,82,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(14,'WEIBO',0,13,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(15,'WEIBO',0,14,48,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(16,'WEIBO',0,15,51,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(17,'WEIBO',0,16,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(18,'WEIBO',0,17,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(19,'WEIBO',0,18,88,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(20,'WEIBO',0,19,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(21,'WEIBO',0,20,96,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(22,'WEIBO',0,21,91,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(23,'WEIBO',0,22,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(24,'WEIBO',0,23,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(25,'XIAOHONGSHU',0,0,42,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(26,'XIAOHONGSHU',0,1,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(27,'XIAOHONGSHU',0,2,48,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(28,'XIAOHONGSHU',0,3,51,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(29,'XIAOHONGSHU',0,4,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(30,'XIAOHONGSHU',0,5,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(31,'XIAOHONGSHU',0,6,42,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(32,'XIAOHONGSHU',0,7,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(33,'XIAOHONGSHU',0,8,48,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(34,'XIAOHONGSHU',0,9,74,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(35,'XIAOHONGSHU',0,10,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(36,'XIAOHONGSHU',0,11,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(37,'XIAOHONGSHU',0,12,80,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(38,'XIAOHONGSHU',0,13,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(39,'XIAOHONGSHU',0,14,48,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(40,'XIAOHONGSHU',0,15,51,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(41,'XIAOHONGSHU',0,16,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(42,'XIAOHONGSHU',0,17,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(43,'XIAOHONGSHU',0,18,42,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(44,'XIAOHONGSHU',0,19,90,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(45,'XIAOHONGSHU',0,20,98,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(46,'XIAOHONGSHU',0,21,94,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(47,'XIAOHONGSHU',0,22,86,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(48,'XIAOHONGSHU',0,23,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(49,'WECHAT_OFFICIAL',0,0,42,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(50,'WECHAT_OFFICIAL',0,1,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(51,'WECHAT_OFFICIAL',0,2,48,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(52,'WECHAT_OFFICIAL',0,3,51,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(53,'WECHAT_OFFICIAL',0,4,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(54,'WECHAT_OFFICIAL',0,5,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(55,'WECHAT_OFFICIAL',0,6,42,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(56,'WECHAT_OFFICIAL',0,7,83,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(57,'WECHAT_OFFICIAL',0,8,90,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(58,'WECHAT_OFFICIAL',0,9,51,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(59,'WECHAT_OFFICIAL',0,10,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(60,'WECHAT_OFFICIAL',0,11,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(61,'WECHAT_OFFICIAL',0,12,76,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(62,'WECHAT_OFFICIAL',0,13,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(63,'WECHAT_OFFICIAL',0,14,48,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(64,'WECHAT_OFFICIAL',0,15,51,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(65,'WECHAT_OFFICIAL',0,16,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(66,'WECHAT_OFFICIAL',0,17,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(67,'WECHAT_OFFICIAL',0,18,82,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(68,'WECHAT_OFFICIAL',0,19,45,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(69,'WECHAT_OFFICIAL',0,20,88,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(70,'WECHAT_OFFICIAL',0,21,51,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(71,'WECHAT_OFFICIAL',0,22,54,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04'),(72,'WECHAT_OFFICIAL',0,23,57,'公开活跃时段经验规则（SIMULATED）',1,'2026-07-21 12:28:04');
/*!40000 ALTER TABLE `activity_prior` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
INSERT INTO `alembic_version` VALUES ('d7bc40428afb');
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `audit_log`
--

DROP TABLE IF EXISTS `audit_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int DEFAULT NULL,
  `action` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `module` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `target_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `request_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `request_method` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ip_address` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `success` tinyint(1) NOT NULL,
  `detail_json` json NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `ix_audit_log_action` (`action`),
  KEY `ix_audit_log_created_at` (`created_at`),
  KEY `ix_audit_log_module` (`module`),
  CONSTRAINT `audit_log_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_log`
--

LOCK TABLES `audit_log` WRITE;
/*!40000 ALTER TABLE `audit_log` DISABLE KEYS */;
INSERT INTO `audit_log` VALUES (1,2,'PUBLISH_NOW','PUBLISH','SCHEDULE','7','/api/schedules/7/publish-now','POST','127.0.0.1',1,'{\"status\": \"MOCK_SUCCESS\"}','2026-07-21 15:24:18');
/*!40000 ALTER TABLE `audit_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `content_article`
--

DROP TABLE IF EXISTS `content_article`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `content_article` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `summary` text COLLATE utf8mb4_unicode_ci,
  `topic` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `target_audience` varchar(150) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `tone` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `keywords_json` json NOT NULL,
  `status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_content_article_created_by` (`created_by`),
  KEY `ix_content_article_status` (`status`),
  KEY `ix_content_article_title` (`title`),
  CONSTRAINT `content_article_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `content_article`
--

LOCK TABLES `content_article` WRITE;
/*!40000 ALTER TABLE `content_article` DISABLE KEYS */;
INSERT INTO `content_article` VALUES (1,'校园新媒体如何建立稳定的内容节奏','校园新媒体团队常常面临选题分散、多人协作断层和发布时间不稳定的问题。建立统一选题池、明确审核节点，并用周度日历安排不同平台版本，可以让内容生产更有秩序。复盘时应记录发布时间、互动率和人工修改耗时，而不是只看点赞总数。','校园新媒体团队常常面临选题分散、多人协作断层和发布时间不稳定的问题。建立统一选题池、明确审核节点，并用周度日历安排不同平台版本，可以让内容生产更有秩序。复盘时应','校园运营','校园新媒体运营者','专业自然','[\"校园运营\", \"内容运营\"]','APPROVED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(2,'AI 辅助写作的三条事实边界','AI 可以帮助提炼结构、转换表达和生成初稿，但不能替代事实核验。涉及人物、数字和研究结论时，应回到原始材料逐项确认。团队还应保留生成版本和人工修改记录，以便复盘效率与质量。','AI 可以帮助提炼结构、转换表达和生成初稿，但不能替代事实核验。涉及人物、数字和研究结论时，应回到原始材料逐项确认。团队还应保留生成版本和人工修改记录，以便复盘','人工智能','校园新媒体运营者','专业自然','[\"人工智能\", \"内容运营\"]','APPROVED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(3,'一次校园摄影展的幕后记录','从征集作品到线下布展，校园摄影展经历了主题讨论、版权确认、作品筛选和空间规划。志愿者团队用两周时间完成一百余幅作品的信息核对，并为每位创作者保留完整署名。','从征集作品到线下布展，校园摄影展经历了主题讨论、版权确认、作品筛选和空间规划。志愿者团队用两周时间完成一百余幅作品的信息核对，并为每位创作者保留完整署名。','校园文化','校园新媒体运营者','专业自然','[\"校园文化\", \"内容运营\"]','APPROVED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(4,'数据复盘不是做一张漂亮图表','有效的数据复盘需要从问题出发。先定义曝光、互动和转化口径，再比较不同平台、内容主题与发布时间。样本量不足时应明确限制，避免把相关性写成因果关系。','有效的数据复盘需要从问题出发。先定义曝光、互动和转化口径，再比较不同平台、内容主题与发布时间。样本量不足时应明确限制，避免把相关性写成因果关系。','数据分析','校园新媒体运营者','专业自然','[\"数据分析\", \"内容运营\"]','APPROVED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(5,'毕业季内容策划清单','毕业季内容可以围绕人物故事、校园记忆、实用服务和仪式现场展开。策划时要提前确认肖像授权、采访时间和发布渠道，并为突发天气和现场变动准备替代方案。','毕业季内容可以围绕人物故事、校园记忆、实用服务和仪式现场展开。策划时要提前确认肖像授权、采访时间和发布渠道，并为突发天气和现场变动准备替代方案。','毕业季','校园新媒体运营者','专业自然','[\"毕业季\", \"内容运营\"]','APPROVED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(6,'社团招新如何减少信息差','清晰的招新内容应说明社团做什么、成员能获得什么、需要投入多少时间，以及报名方式和截止日期。真实活动照片和成员经验比口号更能帮助新生判断是否适合。','清晰的招新内容应说明社团做什么、成员能获得什么、需要投入多少时间，以及报名方式和截止日期。真实活动照片和成员经验比口号更能帮助新生判断是否适合。','社团','校园新媒体运营者','专业自然','[\"社团\", \"内容运营\"]','APPROVED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(7,'一篇长文如何适配三个平台','同一篇长文在微博需要快速给出观点，在小红书需要可扫描的段落和场景化标题，在公众号则要保留完整逻辑。适配不是简单截断，而是在事实一致的前提下重新组织信息。','同一篇长文在微博需要快速给出观点，在小红书需要可扫描的段落和场景化标题，在公众号则要保留完整逻辑。适配不是简单截断，而是在事实一致的前提下重新组织信息。','内容创作','校园新媒体运营者','专业自然','[\"内容创作\", \"内容运营\"]','GENERATED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(8,'校园活动直播的准备流程','活动直播前应检查网络、收音、电源和备用设备，明确导播、摄影与主持分工。还要准备延迟开场、设备掉线等预案，并在结束后及时归档素材和授权记录。','活动直播前应检查网络、收音、电源和备用设备，明确导播、摄影与主持分工。还要准备延迟开场、设备掉线等预案，并在结束后及时归档素材和授权记录。','活动运营','校园新媒体运营者','专业自然','[\"活动运营\", \"内容运营\"]','GENERATED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(9,'如何写出可信的实验结论','实验结论需要说明样本、分组、指标和限制。对照组与实验组应尽量控制其他变量，数据来源必须可追溯。使用模拟数据时应醒目标注，不能与真实结果混合表述。','实验结论需要说明样本、分组、指标和限制。对照组与实验组应尽量控制其他变量，数据来源必须可追溯。使用模拟数据时应醒目标注，不能与真实结果混合表述。','研究方法','校园新媒体运营者','专业自然','[\"研究方法\", \"内容运营\"]','GENERATED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(10,'图书馆夜读空间体验观察','夜读空间延长开放后，学生更关注座位供电、照明、安静程度和离场交通。一次体验观察记录了不同时段的使用情况，也收集了学生对预约方式的建议。','夜读空间延长开放后，学生更关注座位供电、照明、安静程度和离场交通。一次体验观察记录了不同时段的使用情况，也收集了学生对预约方式的建议。','校园生活','校园新媒体运营者','专业自然','[\"校园生活\", \"内容运营\"]','GENERATED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(11,'新媒体团队的素材归档方法','素材归档应统一日期、活动和摄影者命名规则，保留原图、授权信息与使用记录。公共素材库需要设置清晰权限，避免重复下载和来源不明。','素材归档应统一日期、活动和摄影者命名规则，保留原图、授权信息与使用记录。公共素材库需要设置清晰权限，避免重复下载和来源不明。','团队协作','校园新媒体运营者','专业自然','[\"团队协作\", \"内容运营\"]','GENERATED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(12,'从固定发布时间到个性化推荐','固定发布时间易于执行，但不一定适合每个平台和账号。可解释的时间推荐可以结合平台公开活跃规律与账号历史互动数据，给出分数、理由和备选时段，并通过对照实验验证。','固定发布时间易于执行，但不一定适合每个平台和账号。可解释的时间推荐可以结合平台公开活跃规律与账号历史互动数据，给出分数、理由和备选时段，并通过对照实验验证。','时间推荐','校园新媒体运营者','专业自然','[\"时间推荐\", \"内容运营\"]','GENERATED',2,'2026-07-21 12:28:04','2026-07-21 12:28:04');
/*!40000 ALTER TABLE `content_article` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `content_variant`
--

DROP TABLE IF EXISTS `content_variant`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `content_variant` (
  `id` int NOT NULL AUTO_INCREMENT,
  `article_id` int NOT NULL,
  `platform` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `version_no` int NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_html` text COLLATE utf8mb4_unicode_ci,
  `hashtags_json` json NOT NULL,
  `emoji_count` int NOT NULL,
  `word_count` int NOT NULL,
  `model_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `prompt_version` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `generation_duration_ms` int NOT NULL,
  `token_usage` int NOT NULL,
  `quality_score` float NOT NULL,
  `manual_edit_ratio` float NOT NULL,
  `review_status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_generated_text` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_variant_version` (`article_id`,`platform`,`version_no`),
  KEY `ix_content_variant_article_id` (`article_id`),
  KEY `ix_content_variant_platform` (`platform`),
  KEY `ix_content_variant_review_status` (`review_status`),
  CONSTRAINT `content_variant_ibfk_1` FOREIGN KEY (`article_id`) REFERENCES `content_article` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `content_variant`
--

LOCK TABLES `content_variant` WRITE;
/*!40000 ALTER TABLE `content_variant` DISABLE KEYS */;
INSERT INTO `content_variant` VALUES (1,1,'WEIBO',1,'校园新媒体如何建立稳定的内容节奏｜观点速览','校园新媒体如何建立稳定的内容节奏\n\n校园新媒体团队常常面临选题分散、多人协作断层和发布时间不稳定的问题。建立统一选题池、明确审核节点，并用周度日历安排不同平台版本，可以让内容生产更有秩序。复盘时应记录发布时间、互动率和人工修改耗时，而不是只看点赞总数。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#校园运营\", \"#校园新媒体\"]',0,158,'mock-socialflow-v1','1.0.0',320,180,82,0,'APPROVED','校园新媒体如何建立稳定的内容节奏\n\n校园新媒体团队常常面临选题分散、多人协作断层和发布时间不稳定的问题。建立统一选题池、明确审核节点，并用周度日历安排不同平台版本，可以让内容生产更有秩序。复盘时应记录发布时间、互动率和人工修改耗时，而不是只看点赞总数。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(2,1,'XIAOHONGSHU',1,'校园新媒体如何建立稳定的内容节奏｜实用清单','校园新媒体如何建立稳定的内容节奏\n\n校园新媒体团队常常面临选题分散、多人协作断层和发布时间不稳定的问题。建立统一选题池、明确审核节点，并用周度日历安排不同平台版本，可以让内容生产更有秩序。复盘时应记录发布时间、互动率和人工修改耗时，而不是只看点赞总数。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#校园运营\", \"#校园新媒体\"]',0,164,'mock-socialflow-v1','1.0.0',320,180,82,0,'APPROVED','校园新媒体如何建立稳定的内容节奏\n\n校园新媒体团队常常面临选题分散、多人协作断层和发布时间不稳定的问题。建立统一选题池、明确审核节点，并用周度日历安排不同平台版本，可以让内容生产更有秩序。复盘时应记录发布时间、互动率和人工修改耗时，而不是只看点赞总数。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(3,1,'WECHAT_OFFICIAL',1,'校园新媒体如何建立稳定的内容节奏｜深度整理','校园新媒体如何建立稳定的内容节奏\n\n校园新媒体团队常常面临选题分散、多人协作断层和发布时间不稳定的问题。建立统一选题池、明确审核节点，并用周度日历安排不同平台版本，可以让内容生产更有秩序。复盘时应记录发布时间、互动率和人工修改耗时，而不是只看点赞总数。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#校园运营\", \"#校园新媒体\"]',0,168,'mock-socialflow-v1','1.0.0',320,180,82,0,'APPROVED','校园新媒体如何建立稳定的内容节奏\n\n校园新媒体团队常常面临选题分散、多人协作断层和发布时间不稳定的问题。建立统一选题池、明确审核节点，并用周度日历安排不同平台版本，可以让内容生产更有秩序。复盘时应记录发布时间、互动率和人工修改耗时，而不是只看点赞总数。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(4,2,'WEIBO',1,'AI 辅助写作的三条事实边界｜观点速览','AI 辅助写作的三条事实边界\n\nAI 可以帮助提炼结构、转换表达和生成初稿，但不能替代事实核验。涉及人物、数字和研究结论时，应回到原始材料逐项确认。团队还应保留生成版本和人工修改记录，以便复盘效率与质量。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#人工智能\", \"#校园新媒体\"]',0,134,'mock-socialflow-v1','1.0.0',327,185,83,1,'APPROVED','AI 辅助写作的三条事实边界\n\nAI 可以帮助提炼结构、转换表达和生成初稿，但不能替代事实核验。涉及人物、数字和研究结论时，应回到原始材料逐项确认。团队还应保留生成版本和人工修改记录，以便复盘效率与质量。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(5,2,'XIAOHONGSHU',1,'AI 辅助写作的三条事实边界｜实用清单','AI 辅助写作的三条事实边界\n\nAI 可以帮助提炼结构、转换表达和生成初稿，但不能替代事实核验。涉及人物、数字和研究结论时，应回到原始材料逐项确认。团队还应保留生成版本和人工修改记录，以便复盘效率与质量。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#人工智能\", \"#校园新媒体\"]',0,140,'mock-socialflow-v1','1.0.0',327,185,83,1,'APPROVED','AI 辅助写作的三条事实边界\n\nAI 可以帮助提炼结构、转换表达和生成初稿，但不能替代事实核验。涉及人物、数字和研究结论时，应回到原始材料逐项确认。团队还应保留生成版本和人工修改记录，以便复盘效率与质量。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(6,2,'WECHAT_OFFICIAL',1,'AI 辅助写作的三条事实边界｜深度整理','AI 辅助写作的三条事实边界\n\nAI 可以帮助提炼结构、转换表达和生成初稿，但不能替代事实核验。涉及人物、数字和研究结论时，应回到原始材料逐项确认。团队还应保留生成版本和人工修改记录，以便复盘效率与质量。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#人工智能\", \"#校园新媒体\"]',0,144,'mock-socialflow-v1','1.0.0',327,185,83,1,'APPROVED','AI 辅助写作的三条事实边界\n\nAI 可以帮助提炼结构、转换表达和生成初稿，但不能替代事实核验。涉及人物、数字和研究结论时，应回到原始材料逐项确认。团队还应保留生成版本和人工修改记录，以便复盘效率与质量。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(7,3,'WEIBO',1,'一次校园摄影展的幕后记录｜观点速览','一次校园摄影展的幕后记录\n\n从征集作品到线下布展，校园摄影展经历了主题讨论、版权确认、作品筛选和空间规划。志愿者团队用两周时间完成一百余幅作品的信息核对，并为每位创作者保留完整署名。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#校园文化\", \"#校园新媒体\"]',0,123,'mock-socialflow-v1','1.0.0',334,190,84,2,'APPROVED','一次校园摄影展的幕后记录\n\n从征集作品到线下布展，校园摄影展经历了主题讨论、版权确认、作品筛选和空间规划。志愿者团队用两周时间完成一百余幅作品的信息核对，并为每位创作者保留完整署名。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(8,3,'XIAOHONGSHU',1,'一次校园摄影展的幕后记录｜实用清单','一次校园摄影展的幕后记录\n\n从征集作品到线下布展，校园摄影展经历了主题讨论、版权确认、作品筛选和空间规划。志愿者团队用两周时间完成一百余幅作品的信息核对，并为每位创作者保留完整署名。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#校园文化\", \"#校园新媒体\"]',0,129,'mock-socialflow-v1','1.0.0',334,190,84,2,'APPROVED','一次校园摄影展的幕后记录\n\n从征集作品到线下布展，校园摄影展经历了主题讨论、版权确认、作品筛选和空间规划。志愿者团队用两周时间完成一百余幅作品的信息核对，并为每位创作者保留完整署名。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(9,3,'WECHAT_OFFICIAL',1,'一次校园摄影展的幕后记录｜深度整理','一次校园摄影展的幕后记录\n\n从征集作品到线下布展，校园摄影展经历了主题讨论、版权确认、作品筛选和空间规划。志愿者团队用两周时间完成一百余幅作品的信息核对，并为每位创作者保留完整署名。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#校园文化\", \"#校园新媒体\"]',0,133,'mock-socialflow-v1','1.0.0',334,190,84,2,'APPROVED','一次校园摄影展的幕后记录\n\n从征集作品到线下布展，校园摄影展经历了主题讨论、版权确认、作品筛选和空间规划。志愿者团队用两周时间完成一百余幅作品的信息核对，并为每位创作者保留完整署名。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(10,4,'WEIBO',1,'数据复盘不是做一张漂亮图表｜观点速览','数据复盘不是做一张漂亮图表\n\n有效的数据复盘需要从问题出发。先定义曝光、互动和转化口径，再比较不同平台、内容主题与发布时间。样本量不足时应明确限制，避免把相关性写成因果关系。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#数据分析\", \"#校园新媒体\"]',0,119,'mock-socialflow-v1','1.0.0',341,195,85,3,'APPROVED','数据复盘不是做一张漂亮图表\n\n有效的数据复盘需要从问题出发。先定义曝光、互动和转化口径，再比较不同平台、内容主题与发布时间。样本量不足时应明确限制，避免把相关性写成因果关系。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(11,4,'XIAOHONGSHU',1,'数据复盘不是做一张漂亮图表｜实用清单','数据复盘不是做一张漂亮图表\n\n有效的数据复盘需要从问题出发。先定义曝光、互动和转化口径，再比较不同平台、内容主题与发布时间。样本量不足时应明确限制，避免把相关性写成因果关系。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#数据分析\", \"#校园新媒体\"]',0,125,'mock-socialflow-v1','1.0.0',341,195,85,3,'APPROVED','数据复盘不是做一张漂亮图表\n\n有效的数据复盘需要从问题出发。先定义曝光、互动和转化口径，再比较不同平台、内容主题与发布时间。样本量不足时应明确限制，避免把相关性写成因果关系。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(12,4,'WECHAT_OFFICIAL',1,'数据复盘不是做一张漂亮图表｜深度整理','数据复盘不是做一张漂亮图表\n\n有效的数据复盘需要从问题出发。先定义曝光、互动和转化口径，再比较不同平台、内容主题与发布时间。样本量不足时应明确限制，避免把相关性写成因果关系。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#数据分析\", \"#校园新媒体\"]',0,129,'mock-socialflow-v1','1.0.0',341,195,85,3,'APPROVED','数据复盘不是做一张漂亮图表\n\n有效的数据复盘需要从问题出发。先定义曝光、互动和转化口径，再比较不同平台、内容主题与发布时间。样本量不足时应明确限制，避免把相关性写成因果关系。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(13,5,'WEIBO',1,'毕业季内容策划清单｜观点速览','毕业季内容策划清单\n\n毕业季内容可以围绕人物故事、校园记忆、实用服务和仪式现场展开。策划时要提前确认肖像授权、采访时间和发布渠道，并为突发天气和现场变动准备替代方案。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#毕业季\", \"#校园新媒体\"]',0,115,'mock-socialflow-v1','1.0.0',348,200,86,4,'APPROVED','毕业季内容策划清单\n\n毕业季内容可以围绕人物故事、校园记忆、实用服务和仪式现场展开。策划时要提前确认肖像授权、采访时间和发布渠道，并为突发天气和现场变动准备替代方案。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(14,5,'XIAOHONGSHU',1,'毕业季内容策划清单｜实用清单','毕业季内容策划清单\n\n毕业季内容可以围绕人物故事、校园记忆、实用服务和仪式现场展开。策划时要提前确认肖像授权、采访时间和发布渠道，并为突发天气和现场变动准备替代方案。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#毕业季\", \"#校园新媒体\"]',0,121,'mock-socialflow-v1','1.0.0',348,200,86,4,'APPROVED','毕业季内容策划清单\n\n毕业季内容可以围绕人物故事、校园记忆、实用服务和仪式现场展开。策划时要提前确认肖像授权、采访时间和发布渠道，并为突发天气和现场变动准备替代方案。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(15,5,'WECHAT_OFFICIAL',1,'毕业季内容策划清单｜深度整理','毕业季内容策划清单\n\n毕业季内容可以围绕人物故事、校园记忆、实用服务和仪式现场展开。策划时要提前确认肖像授权、采访时间和发布渠道，并为突发天气和现场变动准备替代方案。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#毕业季\", \"#校园新媒体\"]',0,125,'mock-socialflow-v1','1.0.0',348,200,86,4,'APPROVED','毕业季内容策划清单\n\n毕业季内容可以围绕人物故事、校园记忆、实用服务和仪式现场展开。策划时要提前确认肖像授权、采访时间和发布渠道，并为突发天气和现场变动准备替代方案。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(16,6,'WEIBO',1,'社团招新如何减少信息差｜观点速览','社团招新如何减少信息差\n\n清晰的招新内容应说明社团做什么、成员能获得什么、需要投入多少时间，以及报名方式和截止日期。真实活动照片和成员经验比口号更能帮助新生判断是否适合。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#社团\", \"#校园新媒体\"]',0,117,'mock-socialflow-v1','1.0.0',355,205,87,0,'APPROVED','社团招新如何减少信息差\n\n清晰的招新内容应说明社团做什么、成员能获得什么、需要投入多少时间，以及报名方式和截止日期。真实活动照片和成员经验比口号更能帮助新生判断是否适合。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(17,6,'XIAOHONGSHU',1,'社团招新如何减少信息差｜实用清单','社团招新如何减少信息差\n\n清晰的招新内容应说明社团做什么、成员能获得什么、需要投入多少时间，以及报名方式和截止日期。真实活动照片和成员经验比口号更能帮助新生判断是否适合。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#社团\", \"#校园新媒体\"]',0,123,'mock-socialflow-v1','1.0.0',355,205,87,0,'APPROVED','社团招新如何减少信息差\n\n清晰的招新内容应说明社团做什么、成员能获得什么、需要投入多少时间，以及报名方式和截止日期。真实活动照片和成员经验比口号更能帮助新生判断是否适合。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(18,6,'WECHAT_OFFICIAL',1,'社团招新如何减少信息差｜深度整理','社团招新如何减少信息差\n\n清晰的招新内容应说明社团做什么、成员能获得什么、需要投入多少时间，以及报名方式和截止日期。真实活动照片和成员经验比口号更能帮助新生判断是否适合。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#社团\", \"#校园新媒体\"]',0,127,'mock-socialflow-v1','1.0.0',355,205,87,0,'APPROVED','社团招新如何减少信息差\n\n清晰的招新内容应说明社团做什么、成员能获得什么、需要投入多少时间，以及报名方式和截止日期。真实活动照片和成员经验比口号更能帮助新生判断是否适合。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(19,7,'WEIBO',1,'一篇长文如何适配三个平台｜观点速览','一篇长文如何适配三个平台\n\n同一篇长文在微博需要快速给出观点，在小红书需要可扫描的段落和场景化标题，在公众号则要保留完整逻辑。适配不是简单截断，而是在事实一致的前提下重新组织信息。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#内容创作\", \"#校园新媒体\"]',0,122,'mock-socialflow-v1','1.0.0',362,210,88,1,'PENDING','一篇长文如何适配三个平台\n\n同一篇长文在微博需要快速给出观点，在小红书需要可扫描的段落和场景化标题，在公众号则要保留完整逻辑。适配不是简单截断，而是在事实一致的前提下重新组织信息。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(20,7,'XIAOHONGSHU',1,'一篇长文如何适配三个平台｜实用清单','一篇长文如何适配三个平台\n\n同一篇长文在微博需要快速给出观点，在小红书需要可扫描的段落和场景化标题，在公众号则要保留完整逻辑。适配不是简单截断，而是在事实一致的前提下重新组织信息。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#内容创作\", \"#校园新媒体\"]',0,128,'mock-socialflow-v1','1.0.0',362,210,88,1,'PENDING','一篇长文如何适配三个平台\n\n同一篇长文在微博需要快速给出观点，在小红书需要可扫描的段落和场景化标题，在公众号则要保留完整逻辑。适配不是简单截断，而是在事实一致的前提下重新组织信息。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(21,7,'WECHAT_OFFICIAL',1,'一篇长文如何适配三个平台｜深度整理','一篇长文如何适配三个平台\n\n同一篇长文在微博需要快速给出观点，在小红书需要可扫描的段落和场景化标题，在公众号则要保留完整逻辑。适配不是简单截断，而是在事实一致的前提下重新组织信息。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#内容创作\", \"#校园新媒体\"]',0,132,'mock-socialflow-v1','1.0.0',362,210,88,1,'PENDING','一篇长文如何适配三个平台\n\n同一篇长文在微博需要快速给出观点，在小红书需要可扫描的段落和场景化标题，在公众号则要保留完整逻辑。适配不是简单截断，而是在事实一致的前提下重新组织信息。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(22,8,'WEIBO',1,'校园活动直播的准备流程｜观点速览','校园活动直播的准备流程\n\n活动直播前应检查网络、收音、电源和备用设备，明确导播、摄影与主持分工。还要准备延迟开场、设备掉线等预案，并在结束后及时归档素材和授权记录。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#活动运营\", \"#校园新媒体\"]',0,114,'mock-socialflow-v1','1.0.0',369,215,89,2,'PENDING','校园活动直播的准备流程\n\n活动直播前应检查网络、收音、电源和备用设备，明确导播、摄影与主持分工。还要准备延迟开场、设备掉线等预案，并在结束后及时归档素材和授权记录。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(23,8,'XIAOHONGSHU',1,'校园活动直播的准备流程｜实用清单','校园活动直播的准备流程\n\n活动直播前应检查网络、收音、电源和备用设备，明确导播、摄影与主持分工。还要准备延迟开场、设备掉线等预案，并在结束后及时归档素材和授权记录。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#活动运营\", \"#校园新媒体\"]',0,120,'mock-socialflow-v1','1.0.0',369,215,89,2,'PENDING','校园活动直播的准备流程\n\n活动直播前应检查网络、收音、电源和备用设备，明确导播、摄影与主持分工。还要准备延迟开场、设备掉线等预案，并在结束后及时归档素材和授权记录。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(24,8,'WECHAT_OFFICIAL',1,'校园活动直播的准备流程｜深度整理','校园活动直播的准备流程\n\n活动直播前应检查网络、收音、电源和备用设备，明确导播、摄影与主持分工。还要准备延迟开场、设备掉线等预案，并在结束后及时归档素材和授权记录。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#活动运营\", \"#校园新媒体\"]',0,124,'mock-socialflow-v1','1.0.0',369,215,89,2,'PENDING','校园活动直播的准备流程\n\n活动直播前应检查网络、收音、电源和备用设备，明确导播、摄影与主持分工。还要准备延迟开场、设备掉线等预案，并在结束后及时归档素材和授权记录。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(25,9,'WEIBO',1,'如何写出可信的实验结论｜观点速览','如何写出可信的实验结论\n\n实验结论需要说明样本、分组、指标和限制。对照组与实验组应尽量控制其他变量，数据来源必须可追溯。使用模拟数据时应醒目标注，不能与真实结果混合表述。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#研究方法\", \"#校园新媒体\"]',0,117,'mock-socialflow-v1','1.0.0',376,220,82,3,'PENDING','如何写出可信的实验结论\n\n实验结论需要说明样本、分组、指标和限制。对照组与实验组应尽量控制其他变量，数据来源必须可追溯。使用模拟数据时应醒目标注，不能与真实结果混合表述。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(26,9,'XIAOHONGSHU',1,'如何写出可信的实验结论｜实用清单','如何写出可信的实验结论\n\n实验结论需要说明样本、分组、指标和限制。对照组与实验组应尽量控制其他变量，数据来源必须可追溯。使用模拟数据时应醒目标注，不能与真实结果混合表述。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#研究方法\", \"#校园新媒体\"]',0,123,'mock-socialflow-v1','1.0.0',376,220,82,3,'PENDING','如何写出可信的实验结论\n\n实验结论需要说明样本、分组、指标和限制。对照组与实验组应尽量控制其他变量，数据来源必须可追溯。使用模拟数据时应醒目标注，不能与真实结果混合表述。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(27,9,'WECHAT_OFFICIAL',1,'如何写出可信的实验结论｜深度整理','如何写出可信的实验结论\n\n实验结论需要说明样本、分组、指标和限制。对照组与实验组应尽量控制其他变量，数据来源必须可追溯。使用模拟数据时应醒目标注，不能与真实结果混合表述。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#研究方法\", \"#校园新媒体\"]',0,127,'mock-socialflow-v1','1.0.0',376,220,82,3,'PENDING','如何写出可信的实验结论\n\n实验结论需要说明样本、分组、指标和限制。对照组与实验组应尽量控制其他变量，数据来源必须可追溯。使用模拟数据时应醒目标注，不能与真实结果混合表述。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(28,10,'WEIBO',1,'图书馆夜读空间体验观察｜观点速览','图书馆夜读空间体验观察\n\n夜读空间延长开放后，学生更关注座位供电、照明、安静程度和离场交通。一次体验观察记录了不同时段的使用情况，也收集了学生对预约方式的建议。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#校园生活\", \"#校园新媒体\"]',0,112,'mock-socialflow-v1','1.0.0',383,225,83,4,'PENDING','图书馆夜读空间体验观察\n\n夜读空间延长开放后，学生更关注座位供电、照明、安静程度和离场交通。一次体验观察记录了不同时段的使用情况，也收集了学生对预约方式的建议。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(29,10,'XIAOHONGSHU',1,'图书馆夜读空间体验观察｜实用清单','图书馆夜读空间体验观察\n\n夜读空间延长开放后，学生更关注座位供电、照明、安静程度和离场交通。一次体验观察记录了不同时段的使用情况，也收集了学生对预约方式的建议。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#校园生活\", \"#校园新媒体\"]',0,118,'mock-socialflow-v1','1.0.0',383,225,83,4,'PENDING','图书馆夜读空间体验观察\n\n夜读空间延长开放后，学生更关注座位供电、照明、安静程度和离场交通。一次体验观察记录了不同时段的使用情况，也收集了学生对预约方式的建议。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(30,10,'WECHAT_OFFICIAL',1,'图书馆夜读空间体验观察｜深度整理','图书馆夜读空间体验观察\n\n夜读空间延长开放后，学生更关注座位供电、照明、安静程度和离场交通。一次体验观察记录了不同时段的使用情况，也收集了学生对预约方式的建议。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#校园生活\", \"#校园新媒体\"]',0,122,'mock-socialflow-v1','1.0.0',383,225,83,4,'PENDING','图书馆夜读空间体验观察\n\n夜读空间延长开放后，学生更关注座位供电、照明、安静程度和离场交通。一次体验观察记录了不同时段的使用情况，也收集了学生对预约方式的建议。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(31,11,'WEIBO',1,'新媒体团队的素材归档方法｜观点速览','新媒体团队的素材归档方法\n\n素材归档应统一日期、活动和摄影者命名规则，保留原图、授权信息与使用记录。公共素材库需要设置清晰权限，避免重复下载和来源不明。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#团队协作\", \"#校园新媒体\"]',0,108,'mock-socialflow-v1','1.0.0',390,230,84,0,'PENDING','新媒体团队的素材归档方法\n\n素材归档应统一日期、活动和摄影者命名规则，保留原图、授权信息与使用记录。公共素材库需要设置清晰权限，避免重复下载和来源不明。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(32,11,'XIAOHONGSHU',1,'新媒体团队的素材归档方法｜实用清单','新媒体团队的素材归档方法\n\n素材归档应统一日期、活动和摄影者命名规则，保留原图、授权信息与使用记录。公共素材库需要设置清晰权限，避免重复下载和来源不明。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#团队协作\", \"#校园新媒体\"]',0,114,'mock-socialflow-v1','1.0.0',390,230,84,0,'PENDING','新媒体团队的素材归档方法\n\n素材归档应统一日期、活动和摄影者命名规则，保留原图、授权信息与使用记录。公共素材库需要设置清晰权限，避免重复下载和来源不明。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(33,11,'WECHAT_OFFICIAL',1,'新媒体团队的素材归档方法｜深度整理','新媒体团队的素材归档方法\n\n素材归档应统一日期、活动和摄影者命名规则，保留原图、授权信息与使用记录。公共素材库需要设置清晰权限，避免重复下载和来源不明。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#团队协作\", \"#校园新媒体\"]',0,118,'mock-socialflow-v1','1.0.0',390,230,84,0,'PENDING','新媒体团队的素材归档方法\n\n素材归档应统一日期、活动和摄影者命名规则，保留原图、授权信息与使用记录。公共素材库需要设置清晰权限，避免重复下载和来源不明。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(34,12,'WEIBO',1,'从固定发布时间到个性化推荐｜观点速览','从固定发布时间到个性化推荐\n\n固定发布时间易于执行，但不一定适合每个平台和账号。可解释的时间推荐可以结合平台公开活跃规律与账号历史互动数据，给出分数、理由和备选时段，并通过对照实验验证。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#时间推荐\", \"#校园新媒体\"]',0,125,'mock-socialflow-v1','1.0.0',397,235,85,1,'PENDING','从固定发布时间到个性化推荐\n\n固定发布时间易于执行，但不一定适合每个平台和账号。可解释的时间推荐可以结合平台公开活跃规律与账号历史互动数据，给出分数、理由和备选时段，并通过对照实验验证。\n\n这是 WEIBO 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(35,12,'XIAOHONGSHU',1,'从固定发布时间到个性化推荐｜实用清单','从固定发布时间到个性化推荐\n\n固定发布时间易于执行，但不一定适合每个平台和账号。可解释的时间推荐可以结合平台公开活跃规律与账号历史互动数据，给出分数、理由和备选时段，并通过对照实验验证。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#时间推荐\", \"#校园新媒体\"]',0,131,'mock-socialflow-v1','1.0.0',397,235,85,1,'PENDING','从固定发布时间到个性化推荐\n\n固定发布时间易于执行，但不一定适合每个平台和账号。可解释的时间推荐可以结合平台公开活跃规律与账号历史互动数据，给出分数、理由和备选时段，并通过对照实验验证。\n\n这是 XIAOHONGSHU 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04'),(36,12,'WECHAT_OFFICIAL',1,'从固定发布时间到个性化推荐｜深度整理','从固定发布时间到个性化推荐\n\n固定发布时间易于执行，但不一定适合每个平台和账号。可解释的时间推荐可以结合平台公开活跃规律与账号历史互动数据，给出分数、理由和备选时段，并通过对照实验验证。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。',NULL,'[\"#时间推荐\", \"#校园新媒体\"]',0,135,'mock-socialflow-v1','1.0.0',397,235,85,1,'PENDING','从固定发布时间到个性化推荐\n\n固定发布时间易于执行，但不一定适合每个平台和账号。可解释的时间推荐可以结合平台公开活跃规律与账号历史互动数据，给出分数、理由和备选时段，并通过对照实验验证。\n\n这是 WECHAT_OFFICIAL 的 MOCK 演示版本，发布前请人工核验。','2026-07-21 12:28:04','2026-07-21 12:28:04');
/*!40000 ALTER TABLE `content_variant` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `engagement_metric`
--

DROP TABLE IF EXISTS `engagement_metric`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `engagement_metric` (
  `id` int NOT NULL AUTO_INCREMENT,
  `schedule_id` int NOT NULL,
  `platform` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metric_date` date NOT NULL,
  `impressions` int NOT NULL,
  `likes` int NOT NULL,
  `comments` int NOT NULL,
  `collects` int NOT NULL,
  `shares` int NOT NULL,
  `followers` int NOT NULL,
  `engagement_total` int NOT NULL,
  `engagement_rate` float NOT NULL,
  `group_type` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `data_source` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_metric_source_date` (`schedule_id`,`metric_date`,`data_source`),
  KEY `ix_engagement_metric_platform` (`platform`),
  KEY `ix_engagement_metric_schedule_id` (`schedule_id`),
  CONSTRAINT `engagement_metric_ibfk_1` FOREIGN KEY (`schedule_id`) REFERENCES `publish_schedule` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `engagement_metric`
--

LOCK TABLES `engagement_metric` WRITE;
/*!40000 ALTER TABLE `engagement_metric` DISABLE KEYS */;
INSERT INTO `engagement_metric` VALUES (1,1,'WEIBO','2026-07-08',900,43,8,11,8,3000,70,0.077778,'RECOMMENDED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(2,2,'XIAOHONGSHU','2026-07-09',1037,48,9,12,10,3000,79,0.076181,'FIXED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(3,3,'WECHAT_OFFICIAL','2026-07-10',1174,54,10,14,10,3000,88,0.074957,'RECOMMENDED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(4,4,'WEIBO','2026-07-11',1311,60,11,15,11,3000,97,0.073989,'FIXED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(5,5,'XIAOHONGSHU','2026-07-12',1448,65,12,16,13,3000,106,0.073204,'RECOMMENDED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(6,6,'WECHAT_OFFICIAL','2026-07-13',1585,71,13,18,13,3000,115,0.072555,'FIXED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(7,7,'WEIBO','2026-07-14',1722,76,14,19,15,3000,124,0.072009,'RECOMMENDED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(8,8,'XIAOHONGSHU','2026-07-15',1859,82,15,21,15,3000,133,0.071544,'FIXED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(9,9,'WECHAT_OFFICIAL','2026-07-16',1996,88,17,22,15,3000,142,0.071142,'RECOMMENDED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(10,10,'WEIBO','2026-07-17',2133,93,18,24,16,3000,151,0.070792,'FIXED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(11,11,'XIAOHONGSHU','2026-07-18',2270,99,19,25,17,3000,160,0.070485,'RECOMMENDED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(12,12,'WECHAT_OFFICIAL','2026-07-19',2407,104,20,27,18,3000,169,0.070212,'FIXED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(13,13,'WEIBO','2026-07-20',2544,110,21,28,19,3000,178,0.069969,'RECOMMENDED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04'),(14,14,'XIAOHONGSHU','2026-07-21',2681,115,22,29,21,3000,187,0.06975,'FIXED_TIME','SIMULATED','2026-07-21 12:28:04','2026-07-21 12:28:04');
/*!40000 ALTER TABLE `engagement_metric` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `experiment`
--

DROP TABLE IF EXISTS `experiment`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `experiment` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `hypothesis` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_date` date DEFAULT NULL,
  `end_date` date DEFAULT NULL,
  `status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `control_description` text COLLATE utf8mb4_unicode_ci,
  `treatment_description` text COLLATE utf8mb4_unicode_ci,
  `metrics_json` json NOT NULL,
  `result_json` json NOT NULL,
  `conclusion` text COLLATE utf8mb4_unicode_ci,
  `created_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `created_by` (`created_by`),
  CONSTRAINT `experiment_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `experiment`
--

LOCK TABLES `experiment` WRITE;
/*!40000 ALTER TABLE `experiment` DISABLE KEYS */;
INSERT INTO `experiment` VALUES (1,'AI 辅助内容适配效率实验','CONTENT_EFFICIENCY','AI 初稿可减少人工改写耗时','2026-07-14',NULL,'RUNNING','纯人工改写','AI 生成后人工修改','{\"score\": \"适配评分\", \"editCharacters\": \"修改字符数\", \"durationMinutes\": \"完成耗时\"}','{}',NULL,2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(2,'推荐时间与固定时间对比实验','PUBLISH_TIME','推荐时间组的平均互动率更高',NULL,NULL,'DRAFT','每日固定 18:00','系统推荐时间','{\"engagementRate\": \"互动率\"}','{}',NULL,2,'2026-07-21 12:28:04','2026-07-21 12:28:04');
/*!40000 ALTER TABLE `experiment` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `experiment_sample`
--

DROP TABLE IF EXISTS `experiment_sample`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `experiment_sample` (
  `id` int NOT NULL AUTO_INCREMENT,
  `experiment_id` int NOT NULL,
  `schedule_id` int DEFAULT NULL,
  `group_type` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `sample_label` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metric_value_json` json NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `schedule_id` (`schedule_id`),
  KEY `ix_experiment_sample_experiment_id` (`experiment_id`),
  CONSTRAINT `experiment_sample_ibfk_1` FOREIGN KEY (`experiment_id`) REFERENCES `experiment` (`id`) ON DELETE CASCADE,
  CONSTRAINT `experiment_sample_ibfk_2` FOREIGN KEY (`schedule_id`) REFERENCES `publish_schedule` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `experiment_sample`
--

LOCK TABLES `experiment_sample` WRITE;
/*!40000 ALTER TABLE `experiment_sample` DISABLE KEYS */;
INSERT INTO `experiment_sample` VALUES (1,1,NULL,'CONTROL','文章样本 1（SIMULATED）','{\"score\": 80, \"dataSource\": \"SIMULATED\", \"editCharacters\": 620, \"durationMinutes\": 42.0}','2026-07-21 12:28:04'),(2,1,NULL,'CONTROL','文章样本 2（SIMULATED）','{\"score\": 81, \"dataSource\": \"SIMULATED\", \"editCharacters\": 592, \"durationMinutes\": 40.5}','2026-07-21 12:28:04'),(3,1,NULL,'CONTROL','文章样本 3（SIMULATED）','{\"score\": 82, \"dataSource\": \"SIMULATED\", \"editCharacters\": 564, \"durationMinutes\": 39.0}','2026-07-21 12:28:04'),(4,1,NULL,'CONTROL','文章样本 4（SIMULATED）','{\"score\": 83, \"dataSource\": \"SIMULATED\", \"editCharacters\": 536, \"durationMinutes\": 37.5}','2026-07-21 12:28:04'),(5,1,NULL,'CONTROL','文章样本 5（SIMULATED）','{\"score\": 84, \"dataSource\": \"SIMULATED\", \"editCharacters\": 508, \"durationMinutes\": 36.0}','2026-07-21 12:28:04'),(6,1,NULL,'TREATMENT','文章样本 6（SIMULATED）','{\"score\": 85, \"dataSource\": \"SIMULATED\", \"editCharacters\": 480, \"durationMinutes\": 34.5}','2026-07-21 12:28:04'),(7,1,NULL,'TREATMENT','文章样本 7（SIMULATED）','{\"score\": 80, \"dataSource\": \"SIMULATED\", \"editCharacters\": 452, \"durationMinutes\": 33.0}','2026-07-21 12:28:04'),(8,1,NULL,'TREATMENT','文章样本 8（SIMULATED）','{\"score\": 81, \"dataSource\": \"SIMULATED\", \"editCharacters\": 424, \"durationMinutes\": 31.5}','2026-07-21 12:28:04'),(9,1,NULL,'TREATMENT','文章样本 9（SIMULATED）','{\"score\": 82, \"dataSource\": \"SIMULATED\", \"editCharacters\": 396, \"durationMinutes\": 30.0}','2026-07-21 12:28:04'),(10,1,NULL,'TREATMENT','文章样本 10（SIMULATED）','{\"score\": 83, \"dataSource\": \"SIMULATED\", \"editCharacters\": 368, \"durationMinutes\": 28.5}','2026-07-21 12:28:04');
/*!40000 ALTER TABLE `experiment_sample` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `generation_task`
--

DROP TABLE IF EXISTS `generation_task`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `generation_task` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `article_id` int NOT NULL,
  `status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `progress` int NOT NULL,
  `platforms_json` json NOT NULL,
  `result_variant_ids_json` json NOT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `model_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `article_id` (`article_id`),
  CONSTRAINT `generation_task_ibfk_1` FOREIGN KEY (`article_id`) REFERENCES `content_article` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `generation_task`
--

LOCK TABLES `generation_task` WRITE;
/*!40000 ALTER TABLE `generation_task` DISABLE KEYS */;
/*!40000 ALTER TABLE `generation_task` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `media_asset`
--

DROP TABLE IF EXISTS `media_asset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `media_asset` (
  `id` int NOT NULL AUTO_INCREMENT,
  `article_id` int NOT NULL,
  `variant_id` int DEFAULT NULL,
  `source` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `image_url` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `thumbnail_url` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `photographer_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `photographer_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `alt_text` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `search_keyword` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `usage_type` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `selected` tinyint(1) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `variant_id` (`variant_id`),
  KEY `ix_media_asset_article_id` (`article_id`),
  CONSTRAINT `media_asset_ibfk_1` FOREIGN KEY (`article_id`) REFERENCES `content_article` (`id`) ON DELETE CASCADE,
  CONSTRAINT `media_asset_ibfk_2` FOREIGN KEY (`variant_id`) REFERENCES `content_variant` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `media_asset`
--

LOCK TABLES `media_asset` WRITE;
/*!40000 ALTER TABLE `media_asset` DISABLE KEYS */;
/*!40000 ALTER TABLE `media_asset` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `platform_account`
--

DROP TABLE IF EXISTS `platform_account`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `platform_account` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `platform` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `account_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `publish_mode` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `credential_encrypted` text COLLATE utf8mb4_unicode_ci,
  `status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_platform_account_user_id` (`user_id`),
  CONSTRAINT `platform_account_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `platform_account`
--

LOCK TABLES `platform_account` WRITE;
/*!40000 ALTER TABLE `platform_account` DISABLE KEYS */;
INSERT INTO `platform_account` VALUES (1,2,'WEIBO','SocialFlow 演示WEIBO','MOCK',NULL,'ACTIVE','2026-07-21 12:28:04','2026-07-21 12:28:04'),(2,2,'XIAOHONGSHU','SocialFlow 演示XIAOHONGSHU','MOCK',NULL,'ACTIVE','2026-07-21 12:28:04','2026-07-21 12:28:04'),(3,2,'WECHAT_OFFICIAL','SocialFlow 演示WECHAT_OFFICIAL','MOCK',NULL,'ACTIVE','2026-07-21 12:28:04','2026-07-21 12:28:04');
/*!40000 ALTER TABLE `platform_account` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `publish_log`
--

DROP TABLE IF EXISTS `publish_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `publish_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `schedule_id` int NOT NULL,
  `step` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_summary` text COLLATE utf8mb4_unicode_ci,
  `response_summary` text COLLATE utf8mb4_unicode_ci,
  `status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `error_code` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `duration_ms` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_publish_log_schedule_id` (`schedule_id`),
  CONSTRAINT `publish_log_ibfk_1` FOREIGN KEY (`schedule_id`) REFERENCES `publish_schedule` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `publish_log`
--

LOCK TABLES `publish_log` WRITE;
/*!40000 ALTER TABLE `publish_log` DISABLE KEYS */;
INSERT INTO `publish_log` VALUES (1,7,'PUBLISH','WEIBO / variant 7','MOCK：模拟发布成功，未向任何真实平台发送内容','MOCK_SUCCESS',NULL,NULL,57,'2026-07-21 15:24:18');
/*!40000 ALTER TABLE `publish_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `publish_recommendation`
--

DROP TABLE IF EXISTS `publish_recommendation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `publish_recommendation` (
  `id` int NOT NULL AUTO_INCREMENT,
  `article_id` int NOT NULL,
  `variant_id` int DEFAULT NULL,
  `platform` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recommended_at` datetime NOT NULL,
  `score` float NOT NULL,
  `confidence` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason_json` json NOT NULL,
  `alternative_times_json` json NOT NULL,
  `algorithm_version` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `article_id` (`article_id`),
  KEY `variant_id` (`variant_id`),
  CONSTRAINT `publish_recommendation_ibfk_1` FOREIGN KEY (`article_id`) REFERENCES `content_article` (`id`) ON DELETE CASCADE,
  CONSTRAINT `publish_recommendation_ibfk_2` FOREIGN KEY (`variant_id`) REFERENCES `content_variant` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `publish_recommendation`
--

LOCK TABLES `publish_recommendation` WRITE;
/*!40000 ALTER TABLE `publish_recommendation` DISABLE KEYS */;
/*!40000 ALTER TABLE `publish_recommendation` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `publish_schedule`
--

DROP TABLE IF EXISTS `publish_schedule`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `publish_schedule` (
  `id` int NOT NULL AUTO_INCREMENT,
  `article_id` int NOT NULL,
  `variant_id` int NOT NULL,
  `account_id` int DEFAULT NULL,
  `platform` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scheduled_at` datetime NOT NULL,
  `publish_mode` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `retry_count` int NOT NULL,
  `max_retry_count` int NOT NULL,
  `actual_publish_at` datetime DEFAULT NULL,
  `published_url` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `idempotency_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `idempotency_key` (`idempotency_key`),
  KEY `account_id` (`account_id`),
  KEY `created_by` (`created_by`),
  KEY `variant_id` (`variant_id`),
  KEY `ix_publish_schedule_article_id` (`article_id`),
  KEY `ix_publish_schedule_platform` (`platform`),
  KEY `ix_publish_schedule_scheduled_at` (`scheduled_at`),
  KEY `ix_publish_schedule_status` (`status`),
  CONSTRAINT `publish_schedule_ibfk_1` FOREIGN KEY (`account_id`) REFERENCES `platform_account` (`id`) ON DELETE SET NULL,
  CONSTRAINT `publish_schedule_ibfk_2` FOREIGN KEY (`article_id`) REFERENCES `content_article` (`id`) ON DELETE CASCADE,
  CONSTRAINT `publish_schedule_ibfk_3` FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`),
  CONSTRAINT `publish_schedule_ibfk_4` FOREIGN KEY (`variant_id`) REFERENCES `content_variant` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `publish_schedule`
--

LOCK TABLES `publish_schedule` WRITE;
/*!40000 ALTER TABLE `publish_schedule` DISABLE KEYS */;
INSERT INTO `publish_schedule` VALUES (1,1,1,1,'WEIBO','2026-07-21 14:28:00','MOCK','MOCK_SUCCESS',0,3,'2026-07-21 12:28:00','mock://socialflow/published/seed-0',NULL,'849806e8-fae9-4645-8b03-cacbcf7f6289',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(2,1,2,2,'XIAOHONGSHU','2026-07-21 15:28:00','MOCK','MOCK_SUCCESS',0,3,'2026-07-20 12:28:00','mock://socialflow/published/seed-1',NULL,'77eca1df-e7e0-4d0a-9c74-d788ba62ac11',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(3,1,3,3,'WECHAT_OFFICIAL','2026-07-21 16:28:00','MOCK','MOCK_SUCCESS',0,3,'2026-07-19 12:28:00','mock://socialflow/published/seed-2',NULL,'b3c4919a-ea00-43e6-acb6-19d8d128b683',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(4,2,4,1,'WEIBO','2026-07-21 17:28:00','MOCK','MOCK_SUCCESS',0,3,'2026-07-18 12:28:00','mock://socialflow/published/seed-3',NULL,'410f70ad-2cb0-4a46-8953-2e7780581fe9',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(5,2,5,2,'XIAOHONGSHU','2026-07-21 18:28:00','MOCK','MOCK_SUCCESS',0,3,'2026-07-17 12:28:00','mock://socialflow/published/seed-4',NULL,'791fa688-0692-49c3-9bae-d309af305a9f',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(6,2,6,3,'WECHAT_OFFICIAL','2026-07-21 19:28:00','MOCK','MOCK_SUCCESS',0,3,'2026-07-16 12:28:00','mock://socialflow/published/seed-5',NULL,'4e703760-7199-4aba-a0e9-d9ba25055c40',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(7,3,7,1,'WEIBO','2026-07-21 20:28:00','MOCK','MOCK_SUCCESS',0,3,'2026-07-21 15:24:18','mock://socialflow/published/7',NULL,'11912d53-818e-4323-a9fe-9d76d8b36c18',2,'2026-07-21 12:28:04','2026-07-21 15:24:18'),(8,3,8,2,'XIAOHONGSHU','2026-07-21 21:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'70257cb8-23ba-4093-865a-ac9168a88aab',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(9,3,9,3,'WECHAT_OFFICIAL','2026-07-21 22:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'3fd94fd0-f6aa-4109-8656-9d435b32735c',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(10,4,10,1,'WEIBO','2026-07-21 23:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'6a443f0e-c958-4ec2-aae7-298e92b055d5',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(11,4,11,2,'XIAOHONGSHU','2026-07-22 00:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'12447724-ec6d-403e-bc09-0b37e3ec63be',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(12,4,12,3,'WECHAT_OFFICIAL','2026-07-22 01:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'7a452d1c-552f-410c-9134-cf9f5d632c88',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(13,5,13,1,'WEIBO','2026-07-22 02:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'3f7f12b3-b6c7-4559-912a-a31ba4165899',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(14,5,14,2,'XIAOHONGSHU','2026-07-22 03:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'994ddc85-ed31-4c22-8c31-eab9a474b6a1',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(15,5,15,3,'WECHAT_OFFICIAL','2026-07-22 04:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'539c8f9f-9fad-41c3-aec6-4b32ea7af2ab',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(16,6,16,1,'WEIBO','2026-07-22 05:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'1f20f65d-8d16-49c9-82b5-647e7ad4c653',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(17,6,17,2,'XIAOHONGSHU','2026-07-22 06:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'07a379f0-4a2d-484a-ad6a-79a580c42b8b',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(18,6,18,3,'WECHAT_OFFICIAL','2026-07-22 07:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'97b5ad5e-4cd3-4a6e-8a48-868876801212',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(19,7,19,1,'WEIBO','2026-07-22 08:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'9bc43e34-fa5a-4070-9d5f-af4945f11796',2,'2026-07-21 12:28:04','2026-07-21 12:28:04'),(20,7,20,2,'XIAOHONGSHU','2026-07-22 09:28:00','MOCK','PENDING',0,3,NULL,NULL,NULL,'cb513232-e501-4eb1-9661-dfaa0c9b936d',2,'2026-07-21 12:28:04','2026-07-21 12:28:04');
/*!40000 ALTER TABLE `publish_schedule` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sys_role`
--

DROP TABLE IF EXISTS `sys_role`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_role` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_sys_role_code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_role`
--

LOCK TABLES `sys_role` WRITE;
/*!40000 ALTER TABLE `sys_role` DISABLE KEYS */;
INSERT INTO `sys_role` VALUES (1,'ADMIN','管理员','用户、配置、日志和全局统计管理'),(2,'OPERATOR','内容运营者','内容生产、审核、排期和数据复盘'),(3,'VIEWER','查看者','只读访问内容、排期和报告');
/*!40000 ALTER TABLE `sys_role` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sys_user`
--

DROP TABLE IF EXISTS `sys_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_user` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `display_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `avatar_url` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `last_login_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_sys_user_username` (`username`),
  UNIQUE KEY `email` (`email`),
  KEY `ix_sys_user_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_user`
--

LOCK TABLES `sys_user` WRITE;
/*!40000 ALTER TABLE `sys_user` DISABLE KEYS */;
INSERT INTO `sys_user` VALUES (1,'admin','$2b$12$169WEDrOd.ZlQK8M9eG6Ruh4d8hH64WCARHvXzcA86q6VKAqxsdVO','系统管理员','admin@socialflow.local',NULL,'ACTIVE','2026-07-21 11:33:08','2026-07-21 13:06:39','2026-07-21 13:06:39'),(2,'operator','$2b$12$ol97jr9VOV4GN3vIMOisFeOvJXFu89rv.L.VFj2w.sVSSx3cyjiR.','内容运营者','operator@socialflow.local',NULL,'ACTIVE','2026-07-21 11:33:08','2026-07-21 15:23:40','2026-07-21 15:23:40'),(3,'viewer','$2b$12$b.tIoJwEnXbQxciaP4TvJuHKmZhtpQDaZ6wghZZcj1E1qbKXVQ8hi','数据查看者','viewer@socialflow.local',NULL,'ACTIVE','2026-07-21 11:33:08','2026-07-21 11:33:08',NULL);
/*!40000 ALTER TABLE `sys_user` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sys_user_role`
--

DROP TABLE IF EXISTS `sys_user_role`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_user_role` (
  `user_id` int NOT NULL,
  `role_id` int NOT NULL,
  PRIMARY KEY (`user_id`,`role_id`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `sys_user_role_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `sys_role` (`id`) ON DELETE CASCADE,
  CONSTRAINT `sys_user_role_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_user_role`
--

LOCK TABLES `sys_user_role` WRITE;
/*!40000 ALTER TABLE `sys_user_role` DISABLE KEYS */;
INSERT INTO `sys_user_role` VALUES (1,1),(2,2),(3,3);
/*!40000 ALTER TABLE `sys_user_role` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `system_setting`
--

DROP TABLE IF EXISTS `system_setting`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `system_setting` (
  `id` int NOT NULL AUTO_INCREMENT,
  `setting_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `setting_value` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_secret` tinyint(1) NOT NULL,
  `description` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `setting_key` (`setting_key`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `system_setting`
--

LOCK TABLES `system_setting` WRITE;
/*!40000 ALTER TABLE `system_setting` DISABLE KEYS */;
INSERT INTO `system_setting` VALUES (1,'llm.provider','mock',0,'大模型提供方','2026-07-21 12:28:04','2026-07-21 12:28:04'),(2,'llm.base_url','',0,'OpenAI 兼容接口地址','2026-07-21 12:28:04','2026-07-21 12:28:04'),(3,'llm.api_key','',1,'大模型 API Key','2026-07-21 12:28:04','2026-07-21 12:28:04'),(4,'llm.model','',0,'模型名称','2026-07-21 12:28:04','2026-07-21 12:28:04'),(5,'media.unsplash_key','',1,'Unsplash Access Key','2026-07-21 12:28:04','2026-07-21 12:28:04'),(6,'publish.mode','mock',0,'默认发布适配器','2026-07-21 12:28:04','2026-07-21 12:28:04'),(7,'app.timezone','Asia/Shanghai',0,'系统时区','2026-07-21 12:28:04','2026-07-21 12:28:04'),(8,'logs.retention_days','90',0,'日志保留天数','2026-07-21 12:28:04','2026-07-21 12:28:04');
/*!40000 ALTER TABLE `system_setting` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'socialflow'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-07-21 15:28:14
