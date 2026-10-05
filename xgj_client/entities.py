from enum import Enum


class XGJEndpoint(str, Enum):
    TOKEN = "/token"
    CONSUME_DETAILS_BATCH = "/fin/get_receipt_consume_batch"

    STUDENTS_BATCH = "/user/get_student_batch"
    COURSES_BATCH = "/edu/get_shift_batch"
    CLASSES_BATCH = "/edu/get_class_batch"
    ORDERS_BATCH = "/fin/get_order_batch"


class XGJEntity(str, Enum):
    STUDENTS = "students"
    COURSES = "courses"
    CLASSES = "classes"
    CONSUME_DETAILS = "consume_details"
    ORDERS = "orders"
    PAYMENTS = "payments"
