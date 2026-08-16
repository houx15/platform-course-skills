import coverage from "./fixtures/coverage-course.json";
import { CourseDefinition } from "../src/course";

export const validCourse = CourseDefinition.parse((coverage as any).course);
