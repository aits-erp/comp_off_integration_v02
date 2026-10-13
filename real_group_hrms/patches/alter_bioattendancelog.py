import frappe


def execute():
    frappe.db.sql(
        """
        ALTER TABLE `tabbioattendancelog`
        MODIFY COLUMN `name` BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
        MODIFY COLUMN `creation` datetime(6) NULL DEFAULT CURRENT_TIMESTAMP(6),
        MODIFY COLUMN `modified` datetime(6) NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
        MODIFY COLUMN `modified_by` varchar(140) NULL DEFAULT 'Administrator',
        MODIFY COLUMN `owner` varchar(140) NULL DEFAULT 'Administrator'
        """
    )
